"""Spider de Farmacia San Pablo (escalón b, solo listados).

Estrategia (reconocimiento en ``reconocimiento/san_pablo/notas.md``): el sitio
es SAP Commerce con frontend Spartacus y su API OCC
(``api.farmaciasanpablo.com.mx/rest/v2/fsp``) está detrás de Akamai, que solo
deja pasar con huella TLS de Chrome. La búsqueda por categoría
(``query=:relevance:category:{código}``) trae precio, marca, imagen y URL, así
que no se abren fichas, como sí hacía el legado.

La búsqueda está respaldada por Algolia y **corta en 1,000 resultados sin
avisar**: pasada la página 10 responde 200 con ``totalResults = 0``. Una
categoría con más de ``TOPE`` productos se parte en sus subcategorías, que
salen de la faceta plana de códigos (2 dígitos el departamento, 5 la
categoría, 9 la subcategoría) que trae la misma página. Los códigos de
campaña de esa faceta (``APEGO-001``, ``TYPE-…``) no son parte del árbol y se
ignoran.

``basePrice`` es el precio de venta (con descuento) y ``price`` el de lista,
igual que en el legado (``PRECIO_ACTUAL = price``,
``PRECIO_OFERTA = basePrice``). El SKU es ``code`` (18 dígitos con ceros a la
izquierda), el mismo del legado.

Ni la búsqueda ni la ficha reciben sucursal o CP: se captura el precio del
sitio (``zona_precio = sin_ubicacion``), pendiente de confirmar en el
navegador si cambia con el CP.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl sanpablo
    uv run --project scrapers scrapy crawl sanpablo -s CLOSESPIDER_ITEMCOUNT=50
"""
from datetime import datetime, timezone
from decimal import Decimal

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request

from precios_scrapers.spiders.base import SpiderTienda

SITIO = "https://www.farmaciasanpablo.com.mx"
API = "https://api.farmaciasanpablo.com.mx/rest/v2/fsp/products/search"
POR_PAGINA = 100
# El límite por defecto de Algolia: más allá, páginas vacías con 200.
TOPE = 1000
ZONA = "sin_ubicacion"
# Sin este header OCC responde XML. FULL pesa 12% más que DEFAULT y agrega
# brandName.
HEADERS = {"Accept": "application/json"}


def hijas(codigo: str, facetas: list[dict]) -> list[str]:
    """Códigos del nivel inmediato debajo de ``codigo`` en las facetas.

    La faceta trae todo el subárbol revuelto con códigos de campaña; las
    hijas son los numéricos que empiezan con ``codigo`` y tienen el largo más
    corto entre ellos (de 2 se pasa a 5 y de 5 a 9).
    """
    debajo = {valor["name"] for faceta in facetas
              for valor in faceta.get("values", [])
              if valor["name"].isdigit() and valor["name"].startswith(codigo)
              and len(valor["name"]) > len(codigo)}
    if not debajo:
        return []
    largo = min(len(c) for c in debajo)
    return sorted(c for c in debajo if len(c) == largo)


class SpiderSanPablo(SpiderTienda):
    """Categorías -> subcategorías si pasan de 1,000 -> páginas de 100."""

    # El slug de load/config/archivos.yml: así ingesta-v2 lo empata con el
    # histórico.
    name = "sanpablo"
    # Sin cookies, como Guadalajara (ALD-125): las de Akamai (_abck, bm_sv)
    # marcan la sesión y la petición sin ellas pasa igual.
    custom_settings = {"COOKIES_ENABLED": False}

    async def start(self):
        for codigo in self.tienda["categorias"]:
            self.sin_datos.add(codigo)
            yield self.pagina(codigo, codigo, 0)

    def pagina(self, categoria: str, codigo: str,
               numero: int) -> scrapy.Request:
        """``categoria`` es la de tiendas.yml; ``codigo``, la partición."""
        return scrapy.Request(
            f"{API}?query=:relevance:category:{codigo}&pageSize={POR_PAGINA}"
            f"&currentPage={numero}&fields=FULL&lang=es_MX&curr=MXN",
            headers=HEADERS, callback=self.parse,
            cb_kwargs={"categoria": categoria, "codigo": codigo,
                       "numero": numero})

    def parse(self, response, categoria: str, codigo: str, numero: int):
        """Una página; la primera de cada partición decide si baja o pagina."""
        try:
            datos = response.json()
            total = datos["pagination"]["totalResults"]
        except (ValueError, KeyError):
            # 200 con XML o HTML: se pide otra vez antes de perder la página.
            self.logger.warning("Página sin JSON de búsqueda",
                                extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/paginas_sin_datos")
            otra = get_retry_request(response.request, spider=self,
                                     reason="pagina_incompleta")
            if otra is not None:
                yield otra
            return
        if numero == 0 and codigo == categoria:
            self.sin_datos.discard(categoria)
            self.total_reportado = (self.total_reportado or 0) + total
            self.por_categoria[categoria] = {"total_reportado": total,
                                             "skus": set()}
        if numero == 0 and total > TOPE:
            subcodigos = hijas(codigo, datos.get("facets", []))
            if subcodigos:
                # Los productos de esta página vuelven a salir en las hijas.
                # Los que cuelgan de la categoría sin subcategoría (14 en
                # Medicamentos) se pierden y bajan la cobertura.
                # ponytail: recuperarlos por la faceta Precio si la
                # cobertura cae de 98%.
                for subcodigo in subcodigos:
                    yield self.pagina(categoria, subcodigo, 0)
                return
            self.logger.warning("Categoría sin subcategorías con %s productos;"
                                " se recorta a %s", total, TOPE,
                                extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/categorias_recortadas")
        if numero == 0:
            paginas = datos["pagination"]["totalPages"]
            for siguiente in range(1, paginas):
                yield self.pagina(categoria, codigo, siguiente)
        elif total == 0:
            # El corte silencioso de Algolia: no debería pasar con las
            # particiones bajo el tope.
            self.logger.warning("Página vacía tras el tope",
                                extra={"url": response.url})

        ahora = datetime.now(timezone.utc)
        skus = self.por_categoria[categoria]["skus"]
        for producto in datos.get("products", []):
            skus.add(producto["code"])
            yield self.fila(producto, ahora, response.url)

    def fila(self, producto: dict, ahora: datetime, url_fuente: str) -> dict:
        lista = valor(producto.get("price"))
        venta = valor(producto.get("basePrice"))
        # Sin descuento real, un solo precio en precio_lista (contrato v1).
        if lista is None or venta is None or venta >= lista:
            lista, venta = lista or venta, None
        imagen = next((i["url"] for i in producto.get("images", [])
                       if i.get("format") == "product"), None)
        # La URL es la miga: /medicamentos/supervision-medica/a---b---c/
        # <producto>/p/<code>.
        ruta = producto["url"].split("/p/")[0].strip("/").split("/")[:-1]
        presentacion = producto.get("additionalDescription")
        return {
            "capturado_en": ahora,
            "url_producto": SITIO + producto["url"],
            "sku_tienda": producto["code"],
            "producto": producto["name"],
            "marca": producto.get("brandName") or None,
            # OCC no publica EAN.
            "ean": None,
            "categoria_ruta": ruta,
            "precio_lista": lista,
            "precio_oferta": venta,
            "moneda": "MXN",
            "disponible": producto.get("availableForPurchase"),
            "url_imagen": imagen,
            "zona_precio": ZONA,
            "url_fuente": url_fuente,
            "atributos_tienda": ({"presentacion": presentacion}
                                 if presentacion else {}),
        }


def valor(precio: dict | None) -> Decimal | None:
    """``value`` de un precio OCC; None si falta o es 0."""
    if not precio or not precio.get("value"):
        return None
    return Decimal(str(precio["value"]))
