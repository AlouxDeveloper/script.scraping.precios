"""Spider de Farmacias GI (escalón a, solo listados).

Estrategia (reconocimiento en ``reconocimiento/gi/notas.md``): el sitio es
WordPress + WooCommerce sin WAF y la Store API
(``/wp-json/wc/store/v1/products``) está abierta: trae SKU, precio regular,
precio de venta, categorías e imagen, así que el Selenium del legado (listado
y luego ficha por ficha) se reemplaza por páginas JSON de 100.

Las categorías de GI están desordenadas: campañas mezcladas con categorías,
duplicados y 216 productos sin categoría, 101 de ellos con forma
farmacéutica en el nombre. Por eso la categoría ``todo`` de tiendas.yml
recorre el catálogo completo sin filtro; un ID numérico filtra por esa
categoría de WooCommerce.

Los precios vienen en la unidad menor (``"11000"`` = $110.00, según
``currency_minor_unit``) y los nombres con entidades HTML (``H&#038;S``).
WooCommerce tiene un solo precio por producto: no hay sucursal
(``zona_precio = sin_ubicacion``).

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl gi
    uv run --project scrapers scrapy crawl gi -s CLOSESPIDER_ITEMCOUNT=50
"""
import html
from datetime import datetime, timezone
from decimal import Decimal

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request

from precios_scrapers.spiders.base import SpiderTienda

API = "https://farmaciasgi.com.mx/wp-json/wc/store/v1/products"
# El máximo de la Store API: con 101 responde 400.
POR_PAGINA = 100
TODO = "todo"
ZONA = "sin_ubicacion"


class SpiderGi(SpiderTienda):
    """Catálogo completo o categorías -> páginas de 100."""

    name = "gi"

    async def start(self):
        for categoria in self.tienda["categorias"]:
            categoria = str(categoria)
            self.sin_datos.add(categoria)
            yield self.pagina(categoria, 1)

    def pagina(self, categoria: str, numero: int) -> scrapy.Request:
        filtro = "" if categoria == TODO else f"&category={categoria}"
        return scrapy.Request(
            f"{API}?per_page={POR_PAGINA}&page={numero}{filtro}",
            callback=self.parse,
            cb_kwargs={"categoria": categoria, "numero": numero})

    def parse(self, response, categoria: str, numero: int):
        """Una página; la primera pide las demás."""
        total = response.headers.get("x-wp-total")
        paginas = response.headers.get("x-wp-totalpages")
        try:
            productos = response.json()
        except ValueError:
            productos = None
        if total is None or paginas is None or not isinstance(productos,
                                                               list):
            # 200 sin los headers de WooCommerce: página de error de
            # WordPress o recortada. Se pide otra vez.
            self.logger.warning("Página sin listado de la Store API",
                                extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/paginas_sin_datos")
            otra = get_retry_request(response.request, spider=self,
                                     reason="pagina_incompleta")
            if otra is not None:
                yield otra
            return
        if numero == 1:
            total = int(total)
            self.sin_datos.discard(categoria)
            self.total_reportado = (self.total_reportado or 0) + total
            self.por_categoria[categoria] = {"total_reportado": total,
                                             "skus": set()}
            for siguiente in range(2, int(paginas) + 1):
                yield self.pagina(categoria, siguiente)

        ahora = datetime.now(timezone.utc)
        skus = self.por_categoria[categoria]["skus"]
        for producto in productos:
            fila = self.fila(producto, ahora, response.url)
            skus.add(fila["sku_tienda"])
            if fila["precio_lista"] is None:
                # Precio 0 (Flanax 275 mg, 2026-10-15): no se vende hoy.
                self.crawler.stats.inc_value(f"{self.name}/sin_precio")
                continue
            yield fila

    def fila(self, producto: dict, ahora: datetime, url_fuente: str) -> dict:
        precios = producto["prices"]
        escala = 10 ** precios["currency_minor_unit"]
        regular = precio(precios.get("regular_price"), escala)
        venta = precio(precios.get("price"), escala)
        # price 0 con regular_price lleno (Flanax: 0 y 179) es un producto
        # que no se puede comprar, no uno a $179: sin precio.
        if venta is None:
            regular = None
        # Sin descuento real, un solo precio en precio_lista (contrato v1).
        elif regular is None or venta >= regular:
            regular, venta = venta, None
        imagenes = producto.get("images") or [{}]
        # 11 productos sin SKU (Bruluart y otros): el ID de WooCommerce con
        # prefijo, para que no choque con los códigos de 6 dígitos.
        sku = producto.get("sku") or f"wc_{producto['id']}"
        brands = producto.get("brands") or [{}]
        return {
            "capturado_en": ahora,
            "url_producto": producto["permalink"],
            "sku_tienda": sku,
            "producto": html.unescape(producto["name"]),
            "marca": html.unescape(brands[0].get("name", "")) or None,
            # La Store API no publica EAN.
            "ean": None,
            # Las categorías de WooCommerce son planas (y a veces campañas):
            # van todas, no son una miga.
            "categoria_ruta": [html.unescape(c["name"])
                               for c in producto.get("categories", [])],
            "precio_lista": regular,
            "precio_oferta": venta,
            "moneda": "MXN",
            "disponible": producto.get("is_in_stock"),
            "url_imagen": imagenes[0].get("src") or None,
            "zona_precio": ZONA,
            "url_fuente": url_fuente,
            "atributos_tienda": {},
        }


def precio(valor: str | None, escala: int) -> Decimal | None:
    """Precio en unidad menor a pesos; None si falta o es 0."""
    if not valor or not int(valor):
        return None
    return Decimal(int(valor)) / escala
