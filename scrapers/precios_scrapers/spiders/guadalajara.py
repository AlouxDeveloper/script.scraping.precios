"""Spider de Farmacias Guadalajara (escalón b, solo listados).

Estrategia (reconocimiento en ``reconocimiento/guadalajara/notas.md``): el
sitio es SFCC detrás de Akamai, que solo corta por huella TLS y por ritmo, así
que basta HTTP impersonando Chrome. Cada categoría de ``categorias`` en
tiendas.yml es de nivel 2 y su listado incluye todo su subárbol; se recorre
con ``?start=N&sz=96`` hasta el total que reporta ("N productos"). Las
tarjetas del listado, renderizadas en servidor, traen ID, nombre, marca,
imagen, precio tachado y precio de venta, así que no se abren fichas.

No se usa ``Search-UpdateGrid`` (el botón "Más resultados"): está bajo
``/on/demandware.store/``, que robots.txt prohíbe; la URL SEO de la categoría
acepta los mismos ``start`` y ``sz``.

Sin ubicación el sitio da su precio online y no hay sucursal que fijar
(``zona_precio = sin_ubicacion``). La disponibilidad tampoco es confiable sin
código postal (fichas en ``OutOfStock`` con el botón "Agregar" visible), así
que ``disponible`` va vacío.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl guadalajara
    uv run --project scrapers scrapy crawl guadalajara -s CLOSESPIDER_ITEMCOUNT=50
"""
import re
from datetime import datetime, timezone
from decimal import Decimal

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request

from precios_scrapers.spiders.base import SpiderTienda

SITIO = "https://www.farmaciasguadalajara.com"
# 96 es el tamaño medido en el reconocimiento (p50 2.6 s, ~1 MB). Uno mayor
# ahorra peticiones pero cada respuesta pesa y tarda más (sz=600: 13.8 s).
POR_PAGINA = 96
ZONA = "sin_ubicacion"
TOTAL = re.compile(r"([\d,]+)\s+productos")


def total_productos(response) -> int | None:
    """El "N productos" del listado, o None si la página no lo trae."""
    encontrado = TOTAL.search(response.text)
    return int(encontrado.group(1).replace(",", "")) if encontrado else None


def precio(tarjeta, selector: str) -> Decimal | None:
    valor = tarjeta.css(f"{selector} .value::attr(content)").get()
    return Decimal(valor) if valor else None


class SpiderGuadalajara(SpiderTienda):
    """Categorías de nivel 2 -> páginas de 96 -> productos."""

    name = "guadalajara"
    # Sin cookies: cada petición llega como visitante nuevo. En ALD-125, tras
    # 33 páginas Akamai empezó a resetear todas las de la sesión, también
    # después de esperas de 120 s, mientras la misma URL sin cookies daba 200.
    # El handler abre una sesión de curl por petición, así que lo único que
    # arrastraba la sesión marcada eran las cookies (_abck, bm_sv).
    custom_settings = {"COOKIES_ENABLED": False}

    async def start(self):
        for ruta in self.tienda["categorias"]:
            yield self.pagina(ruta, 0)

    def pagina(self, categoria: str, inicio: int) -> scrapy.Request:
        return scrapy.Request(
            f"{SITIO}{categoria}?start={inicio}&sz={POR_PAGINA}",
            callback=self.parse,
            cb_kwargs={"categoria": categoria, "inicio": inicio})

    def parse(self, response, categoria: str, inicio: int):
        """Una página de una categoría; la primera pide las demás."""
        total = total_productos(response)
        if total is None:
            # Una respuesta 200 sin listado (página de error o recortada):
            # se pide otra vez antes de perder la categoría entera.
            self.logger.warning("Página sin total de productos",
                                extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/paginas_sin_datos")
            otra = get_retry_request(response.request, spider=self,
                                     reason="pagina_incompleta")
            if otra is not None:
                yield otra
            return
        if inicio == 0:
            self.total_reportado = (self.total_reportado or 0) + total
            self.por_categoria[categoria] = {"total_reportado": total,
                                             "skus": set()}
            for siguiente in range(POR_PAGINA, total, POR_PAGINA):
                yield self.pagina(categoria, siguiente)

        ruta = [paso.strip() for paso in
                response.css(".breadcrumb a::text").getall()
                if paso.strip() and paso.strip() != "Inicio"]
        ahora = datetime.now(timezone.utc)
        skus = self.por_categoria[categoria]["skus"]
        tarjetas = response.css("div.product[data-pid]")
        if not tarjetas:
            self.logger.warning("Página de listado sin productos",
                                extra={"url": response.url})
        for tarjeta in tarjetas:
            skus.add(tarjeta.attrib["data-pid"])
            yield self.fila(tarjeta, ahora, response.url, ruta)

    def fila(self, tarjeta, ahora: datetime, url_fuente: str,
             ruta: list[str]) -> dict:
        antes = precio(tarjeta, ".price-before")
        actual = precio(tarjeta, ".sales")
        # El sitio muestra un precio tachado en casi todo; solo es lista si
        # de verdad es mayor que el de venta (contrato v1).
        if antes is not None and (actual is None or antes <= actual):
            antes = None
        enlace = tarjeta.css(".pdp-link a")
        imagen = tarjeta.css("img.tile-image::attr(src)").get()
        promocion = " ".join(" ".join(
            tarjeta.css(".promotions ::text").getall()).split())
        return {
            "capturado_en": ahora,
            "url_producto": SITIO + enlace.attrib["href"],
            "sku_tienda": tarjeta.attrib["data-pid"],
            "producto": " ".join(enlace.css("::text").get("").split()),
            "marca": " ".join(tarjeta.css(".plp-brand::text").get("")
                              .split()) or None,
            # Ni la tarjeta ni la ficha traen EAN (reconocimiento).
            "ean": None,
            "categoria_ruta": ruta,
            "precio_lista": antes or actual,
            "precio_oferta": actual if antes else None,
            "moneda": "MXN",
            "disponible": None,
            # Sin los parámetros de miniatura (?w=180&h=180), la imagen grande.
            "url_imagen": imagen.split("?")[0] if imagen else None,
            "zona_precio": ZONA,
            "url_fuente": url_fuente,
            "atributos_tienda": {"promocion": promocion} if promocion else {},
        }
