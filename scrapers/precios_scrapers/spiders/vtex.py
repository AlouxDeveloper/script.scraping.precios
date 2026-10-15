"""Base VTEX de Scrapers 2.0 y spider de Chedraui (escalón a, solo listados).

Estrategia (reconocimiento en ``reconocimiento/chedraui/notas.md`` y los de
Farmatodo, Klyns y Similares): todas las tiendas VTEX responden la API
pública ``/api/catalog_system/pub/products/search`` sin cookies ni
impersonación, y el listado trae precio, precio de lista, EAN, marca, imagen y
ruta de categorías, así que no se abren fichas.

Se usa ``catalog_system`` y no Intelligent Search porque es la única que
permiten todas: el robots.txt de Farmatodo prohíbe ``/*?``, que cubre la
búsqueda, y permite expresamente ``/api/catalog_system/pub/products/search``.
En Chedraui las dos dan el mismo precio al centavo (37 de 37 productos de
Diabéticos, 2026-10-15).

Cada categoría de tiendas.yml es una ruta de IDs (``/4/403/``, la de
``fq=C:``). El total sale del header ``resources`` (``0-49/3384``). La API no
deja pasar de ``_from=2500``: una categoría con más de ``TOPE`` productos se
parte por rango de precio (``fq=P:[a TO b]``) hasta que cada rango cabe, y no
por subcategorías, porque hay productos colgados de la categoría padre sin
subcategoría que así se perderían (6 en Farmacia de Chedraui).

Lo propio de cada tienda va en tiendas.yml: ``dominio``, ``campo_sku`` (el
campo que el legado guardaba como SKU, para que el histórico empate) y
``zona_precio``. Una tienda nueva solo necesita una subclase con su ``name``.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl chedraui
    uv run --project scrapers scrapy crawl chedraui -s CLOSESPIDER_ITEMCOUNT=50
"""
import re
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request

from precios_scrapers.spiders.base import SpiderTienda

RUTA_API = "/api/catalog_system/pub/products/search"
POR_PAGINA = 50
# _from admite hasta 2500; con páginas de 50, el último producto alcanzable
# es el 2,550.
TOPE = 2550
# Rango inicial de precio en centavos ($0 a $100,000). Los cortes son enteros
# en centavos para que los rangos no se traslapen ni dejen huecos.
PRECIO_MAXIMO = 10_000_000
RESOURCES = re.compile(r"/(\d+)$")


def total_resources(response) -> int | None:
    """El total del header ``resources`` o None si no viene."""
    valor = response.headers.get("resources", b"").decode()
    encontrado = RESOURCES.search(valor)
    return int(encontrado.group(1)) if encontrado else None


def a_pesos(centavos: int) -> str:
    return f"{centavos / 100:.2f}"


class SpiderVtex(SpiderTienda):
    """Categorías -> rangos de precio si hace falta -> páginas de 50."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.dominio = self.tienda["dominio"]
        self.campo_sku = self.tienda["campo_sku"]
        self.zona = self.tienda["zona_precio"]

    async def start(self):
        for ruta in self.tienda["categorias"]:
            self.sin_datos.add(ruta)
            yield self.pedir(ruta, None, 0)

    def pedir(self, categoria: str, rango: tuple[int, int] | None,
              inicio: int) -> scrapy.Request:
        # Se arma a mano: el corchete y el espacio del filtro de precio deben
        # ir como %20; con "+" la API responde 400.
        url = f"{self.dominio}{RUTA_API}?fq=C:{categoria}"
        if rango is not None:
            url += (f"&fq=P:%5B{a_pesos(rango[0])}%20TO%20"
                    f"{a_pesos(rango[1])}%5D")
        url += f"&_from={inicio}&_to={inicio + POR_PAGINA - 1}"
        return scrapy.Request(
            url, callback=self.parse,
            cb_kwargs={"categoria": categoria, "rango": rango,
                       "inicio": inicio})

    def parse(self, response, categoria: str,
              rango: tuple[int, int] | None, inicio: int):
        """Una página; la primera de cada rango decide si parte o pagina."""
        total = total_resources(response)
        if total is None:
            # 200 sin header: respuesta de error o recortada. Se pide otra
            # vez antes de perder el rango entero.
            self.logger.warning("Página sin header resources",
                                extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/paginas_sin_datos")
            otra = get_retry_request(response.request, spider=self,
                                     reason="pagina_incompleta")
            if otra is not None:
                yield otra
            return
        productos = response.json()
        if inicio == 0 and rango is None:
            self.sin_datos.discard(categoria)
            self.total_reportado = (self.total_reportado or 0) + total
            self.por_categoria[categoria] = {"total_reportado": total,
                                             "skus": set()}
        if inicio == 0 and total > TOPE:
            # Los productos de esta página vuelven a salir en los rangos.
            mitades = self.partir(rango or (0, PRECIO_MAXIMO), productos)
            if mitades:
                for mitad in mitades:
                    yield self.pedir(categoria, mitad, 0)
                return
            # Más de 2,550 productos con el mismo precio: se pierde el resto.
            self.logger.warning("Rango de precio sin partir con %s productos",
                                total, extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/rangos_recortados")
        if inicio == 0:
            for siguiente in range(POR_PAGINA, min(total, TOPE), POR_PAGINA):
                yield self.pedir(categoria, rango, siguiente)

        ahora = datetime.now(timezone.utc)
        skus = self.por_categoria[categoria]["skus"]
        for producto in productos:
            if not producto.get("items"):
                # Producto sin SKU activo: VTEX lo lista pero no lo vende.
                self.crawler.stats.inc_value(f"{self.name}/sin_items")
                continue
            fila = self.fila(producto, ahora, response.url)
            skus.add(fila["sku_tienda"])
            if fila["precio_lista"] is None:
                # Sin precio el producto no se vende hoy; no hay qué guardar.
                self.crawler.stats.inc_value(f"{self.name}/sin_precio")
                continue
            yield fila

    @staticmethod
    def partir(rango: tuple[int, int], productos: list[dict]) -> list | None:
        """Parte ``rango`` (centavos) en dos o devuelve None si no se puede.

        Corta en la mediana de los precios de la página, una muestra del
        rango, y si cae fuera, a la mitad: casi todo cuesta menos de $500 y
        el rango inicial llega a $100,000.
        """
        minimo, maximo = rango
        if minimo >= maximo:
            return None
        precios = [precio_venta(p) for p in productos if p.get("items")]
        precios = [int(p * 100) for p in precios if p]
        corte = int(median(precios)) if precios else minimo
        if not minimo <= corte < maximo:
            corte = (minimo + maximo) // 2
        return [(minimo, corte), (corte + 1, maximo)]

    def sku(self, producto: dict) -> str | None:
        """El campo ``campo_sku`` del producto o de su primer ítem."""
        valor = producto.get(self.campo_sku)
        if valor is None:
            valor = producto["items"][0].get(self.campo_sku)
        # None deja que el contrato rechace la fila (nulo/sku_tienda).
        return str(valor) if valor else None

    def fila(self, producto: dict, ahora: datetime, url_fuente: str) -> dict:
        item = producto["items"][0]
        oferta = item["sellers"][0]["commertialOffer"]
        actual = precio_venta(producto)
        lista = Decimal(str(oferta["ListPrice"])) if oferta["ListPrice"] else None
        # Sin descuento real el ListPrice no cuenta (contrato v1).
        if lista is not None and (actual is None or lista <= actual):
            lista = None
        imagen = (item.get("images") or [{}])[0].get("imageUrl")
        ean = item.get("ean") or None
        # categories trae la ruta de cada nivel ("/Farmacia/Medicamentos/");
        # la más larga es la miga completa.
        ruta = max(producto.get("categories") or ["/"], key=len)
        return {
            "capturado_en": ahora,
            "url_producto": producto["link"],
            "sku_tienda": self.sku(producto),
            "producto": producto["productName"],
            "marca": producto.get("brand") or None,
            "ean": ean if ean and ean.isdigit() else None,
            "categoria_ruta": [paso for paso in ruta.split("/") if paso],
            "precio_lista": lista or actual,
            "precio_oferta": actual if lista else None,
            "moneda": "MXN",
            "disponible": oferta.get("IsAvailable"),
            # Sin ?v=…, que solo cambia con la versión de la imagen.
            "url_imagen": imagen.split("?")[0] if imagen else None,
            "zona_precio": self.zona,
            "url_fuente": url_fuente,
            "atributos_tienda": {},
        }


def precio_venta(producto: dict) -> Decimal | None:
    """``Price`` del primer vendedor; None si es 0 (sin existencia)."""
    valor = producto["items"][0]["sellers"][0]["commertialOffer"]["Price"]
    return Decimal(str(valor)) if valor else None


class SpiderChedraui(SpiderVtex):
    name = "chedraui"
