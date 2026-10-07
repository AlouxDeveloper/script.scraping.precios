"""Spider de Walmart México (escalón d, solo listados).

Estrategia (reconocimiento en ``reconocimiento/walmart/notas.md``): cada rama
de ``categorias`` en tiendas.yml lista sus hojas en la faceta ``cat_id``; cada
hoja se parte por rango de precio hasta que cada segmento cabe en una página,
y el ``__NEXT_DATA__`` del listado trae precio, EAN (``usItemId``) y
vendedor, así que no se abren fichas.

No se pagina (medido en ALD-121 con Antigripales, 185 productos): las páginas
2..N pierden productos y sin filtro cada página mete 6 anuncios que desplazan
a 6 orgánicos. Recorrer sus 5 páginas dio 146 únicos; partirla en segmentos
``min_price``/``max_price`` de una página, 183. Con filtro de precio el sitio
no mete anuncios. Los bordes entran en ambos segmentos y el pipeline
deduplica; el corte va en la mediana de los precios vistos, porque casi todo
cuesta menos de $500 y la faceta de precio llega a decenas de miles.

La sucursal es la que el sitio asigna por la IP (decisión de Aldo, igual que
el legado). La primera página fija la sucursal de la corrida y va en
``zona_precio``; si una página posterior trae otra, la corrida se cierra
como parcial. Con ``sucursal`` en tiendas.yml se exige esa desde el inicio.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl walmart
    uv run --project scrapers scrapy crawl walmart -s CLOSESPIDER_ITEMCOUNT=50
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median

import scrapy
from scrapy.exceptions import CloseSpider
from w3lib.url import add_or_replace_parameters

from precios_scrapers.spiders.base import SpiderTienda

SITIO = "https://www.walmart.com.mx"
POR_PAGINA = 40
# maxPage nunca pasa de 23; solo importa si un segmento de un peso de ancho
# sigue sin caber y hay que paginarlo.
TOPE_PAGINAS = 23


def datos_listado(response) -> dict | None:
    """``initialData`` del ``__NEXT_DATA__`` o None si la página no lo trae."""
    texto = response.css("script#__NEXT_DATA__::text").get()
    if not texto:
        return None
    return json.loads(texto)["props"]["pageProps"].get("initialData")


def facetas(nodo):
    """Recorre todas las facetas de la página.

    Según el nivel del listado, ``allSortAndFilterFacets`` cuelga de
    ``searchResult.modules`` o de ``contentLayout.modules[n].configs``.
    """
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if clave == "allSortAndFilterFacets" and valor:
                yield from valor
            else:
                yield from facetas(valor)
    elif isinstance(nodo, list):
        for valor in nodo:
            yield from facetas(valor)


def faceta(datos: dict, tipo: str) -> dict | None:
    return next((f for f in facetas(datos) if f["type"] == tipo), None)


def organicos(busqueda: dict) -> list[dict]:
    """Productos del listado sin anuncios.

    Sin filtro de precio, cada página trae un ``AdPlaceholder`` y 6
    patrocinados (``isSponsoredFlag``), repetidos en todas las páginas y a
    veces de otra hoja: no son del listado y se descartan.
    """
    return [item for pila in busqueda["itemStacks"] for item in pila["items"]
            if item.get("__typename") == "Product"
            and not item.get("isSponsoredFlag")]


def precio(texto: str) -> Decimal | None:
    """"$1,234.00" -> Decimal("1234.00"); vacío -> None."""
    limpio = texto.replace("$", "").replace(",", "").strip()
    return Decimal(limpio) if limpio else None


class SpiderWalmart(SpiderTienda):
    """Ramas -> hojas -> páginas (o segmentos de precio) -> productos."""

    name = "walmart"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sucursal = self.tienda["sucursal"]

    async def start(self):
        for ruta in self.tienda["categorias"]:
            yield scrapy.Request(SITIO + ruta, callback=self.parse_rama)

    def parse_rama(self, response):
        datos = self.leer(response)
        if datos is None:
            return
        busqueda = datos["searchResult"]
        self.total_reportado = ((self.total_reportado or 0)
                                + busqueda["aggregatedCount"])
        rama = [paso["name"] for paso in busqueda.get("breadCrumb") or []]
        for hoja in faceta(datos, "cat_id")["values"]:
            yield scrapy.Request(
                SITIO + hoja["baseSeoURL"], callback=self.parse_listado,
                cb_kwargs={"hoja": hoja["id"],
                           "ruta": [*rama, hoja["name"]]})

    def parse_listado(self, response, hoja: str, ruta: list[str],
                      segmento=None, pagina: int = 1, techo=None):
        """Una página de una hoja o de un segmento de precio de la hoja.

        ``segmento`` es ``(minimo, maximo)`` con ``maximo`` None si es
        abierto; ``techo`` es el precio máximo de la hoja según su faceta y
        sirve para partir el segmento abierto.
        """
        datos = self.leer(response)
        if datos is None:
            return
        busqueda = datos["searchResult"]
        total = busqueda["aggregatedCount"]
        # La página 1 sin segmento da el total de la hoja; va antes de los
        # productos para que sus SKU ya cuenten en la cobertura.
        if pagina == 1 and segmento is None:
            self.por_categoria.setdefault(hoja, {"total_reportado": total,
                                                 "skus": set()})
            techo = (faceta(datos, "price") or {}).get("max")
        items = organicos(busqueda)
        yield from self.productos(items, response, hoja, ruta)
        if pagina > 1 or total <= POR_PAGINA:
            return

        precios = [item["price"] for item in items if item.get("price")]
        mitades = self.partir(segmento or (0, None), techo, precios)
        if mitades:
            for mitad in mitades:
                yield self.pedir(response.url, hoja, ruta, mitad, 1, techo)
            return
        # Más de 40 productos con el mismo precio: no queda más que paginar.
        self.logger.warning("Segmento de precio sin partir con %s productos",
                            total, extra={"url": response.url})
        self.crawler.stats.inc_value("walmart/segmentos_paginados")
        paginas = busqueda["paginationV2"]["maxPage"]
        for n in range(2, min(paginas, TOPE_PAGINAS) + 1):
            yield self.pedir(response.url, hoja, ruta, segmento, n, techo)

    @staticmethod
    def partir(segmento, techo, precios: list) -> list | None:
        """Parte ``segmento`` en dos o devuelve None si ya no se puede.

        Corta en la mediana de ``precios`` (los de la página, una muestra del
        segmento) y, si cae fuera del segmento, a la mitad del rango. El
        borde va en las dos mitades: un precio igual al corte sale en ambas
        y el pipeline lo deduplica, pero ninguno se pierde.
        """
        minimo, maximo = segmento
        tope = maximo if maximo is not None else techo
        if tope is None:
            return None
        corte = int(median(precios)) if precios else minimo
        if not minimo < corte < tope:
            corte = (minimo + tope) // 2
        if corte <= minimo:
            return None
        return [(minimo, corte), (corte, maximo)]

    def pedir(self, url: str, hoja: str, ruta: list[str], segmento,
              pagina: int, techo) -> scrapy.Request:
        parametros = {"page": str(pagina)} if pagina > 1 else {}
        if segmento is not None:
            minimo, maximo = segmento
            parametros["min_price"] = str(minimo)
            if maximo is not None:
                parametros["max_price"] = str(maximo)
        base = url.split("?")[0]
        return scrapy.Request(
            add_or_replace_parameters(base, parametros),
            callback=self.parse_listado,
            cb_kwargs={"hoja": hoja, "ruta": ruta, "segmento": segmento,
                       "pagina": pagina, "techo": techo})

    def leer(self, response) -> dict | None:
        """Datos del listado tras verificar la sucursal de la página."""
        datos = datos_listado(response)
        busqueda = (datos or {}).get("searchResult")
        if not busqueda:
            self.logger.warning("Página sin __NEXT_DATA__ de listado",
                                extra={"url": response.url})
            self.crawler.stats.inc_value("walmart/paginas_sin_datos")
            return None
        tienda = busqueda["paginationV2"]["pageProperties"].get("stores")
        if self.sucursal is None:
            self.sucursal = tienda
            self.logger.info("Sucursal de la corrida: %s", tienda)
        elif tienda != self.sucursal:
            self.logger.error("La página trae la sucursal %s y la corrida "
                              "es de la %s", tienda, self.sucursal,
                              extra={"url": response.url})
            raise CloseSpider("sucursal_cambiada")
        return datos

    def productos(self, items: list[dict], response, hoja: str,
                  ruta: list[str]):
        ahora = datetime.now(timezone.utc)
        cobertura = self.por_categoria.get(hoja)
        for item in items:
            if cobertura is not None:
                cobertura["skus"].add(item["usItemId"])
            yield self.fila(item, ahora, response.url, ruta)

    def fila(self, item: dict, ahora: datetime, url_fuente: str,
             ruta: list[str]) -> dict:
        info = item["priceInfo"]
        actual = Decimal(str(item["price"])) if item.get("price") else None
        antes = precio(info.get("wasPrice") or "")
        # Sin descuento real, el precio tachado no cuenta (contrato v1).
        if antes is not None and (actual is None or antes <= actual):
            antes = None
        sku = item["usItemId"]
        atributos = {"vendedor": item.get("sellerName"),
                     "tipo_vendedor": item.get("sellerType"),
                     "precio_rango": info.get("priceRangeString")}
        return {
            "capturado_en": ahora,
            "url_producto": SITIO + item["canonicalUrl"],
            "sku_tienda": sku,
            "producto": item["name"],
            "marca": item.get("brand") or None,
            # usItemId = upc = gtin13 en las fichas revisadas (notas.md).
            "ean": sku if sku.isdigit() else None,
            "categoria_ruta": ruta,
            "precio_lista": antes or actual,
            "precio_oferta": actual if antes else None,
            "moneda": "MXN",
            "disponible": item["availabilityStatusV2"]["value"] == "IN_STOCK",
            "url_imagen": (item.get("imageInfo") or {}).get("thumbnailUrl"),
            "zona_precio": self.sucursal,
            "url_fuente": url_fuente,
            "atributos_tienda": {k: v for k, v in atributos.items() if v},
        }
