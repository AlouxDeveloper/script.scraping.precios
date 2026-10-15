"""Spider de Farmacias ISSEG (escalón b, solo listados).

Estrategia (reconocimiento en ``reconocimiento/isseg/notas.md``): el sitio es
Angular sobre una API ASP.NET
(``sapipedidossissegp.farmaciasisseg.com.mx/sapipedidossisseg/api``) detrás
de SafeLine (Chaitin), que responde HTTP 468 con un CAPTCHA deslizable salvo
que la petición traiga huella TLS de Chrome **y** ``Referer`` del sitio. No
limitó por ritmo en el reconocimiento. Sin ``Accept: application/json`` la
API responde XML.

Hay dos listados y tiendas.yml elige cuáles usar:

- ``categorias``: IDs de ``categorias/{id}``. Devuelve **como máximo 50
  productos y no pagina** (ignora ``pagina``, ``skip``, ``top``…). Es lo que
  capturaba el legado: 612 de unos 13,000.
- ``busquedas``: términos para ``POST productos/busqueda``, que busca en el
  nombre y el principio activo. Tope de 100 resultados y 404 con cuerpo
  vacío cuando no hay ninguno. Es la única vía para cubrir el catálogo.

Ninguno de los dos reporta un total: la cobertura de cada partición es lo que
devolvió contra sí misma, y una búsqueda que llega a 100 queda marcada
porque pudo haberse recortado.

Las dos respuestas traen la imagen en base64 (~128 KB por producto) y la API
no publica una URL de imagen: ``url_imagen`` va vacío y el base64 nunca se
guarda. El SKU es ``codigoBarras``, el mismo del legado. El precio no depende
de sucursal ni de CP (``zona_precio = sin_ubicacion``).

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl isseg
    uv run --project scrapers scrapy crawl isseg -s CLOSESPIDER_ITEMCOUNT=50
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request

from precios_scrapers.spiders.base import SpiderTienda

SITIO = "https://farmaciasisseg.com.mx"
API = "https://sapipedidossissegp.farmaciasisseg.com.mx/sapipedidossisseg/api"
# Sin Referer SafeLine responde 468 aunque la huella sea de Chrome.
HEADERS = {"Accept": "application/json", "Referer": f"{SITIO}/"}
TOPE_BUSQUEDA = 100
ZONA = "sin_ubicacion"


class SpiderIsseg(SpiderTienda):
    """Categorías (50 cada una) y búsquedas (hasta 100 cada una)."""

    name = "isseg"

    async def start(self):
        for ident in self.tienda.get("categorias", []):
            clave = f"categoria:{ident}"
            self.sin_datos.add(clave)
            yield scrapy.Request(f"{API}/categorias/{ident}", headers=HEADERS,
                                 callback=self.parse, cb_kwargs={"clave": clave})
        for termino in self.tienda.get("busquedas", []):
            clave = f"busqueda:{termino}"
            self.sin_datos.add(clave)
            yield scrapy.Request(
                f"{API}/productos/busqueda", method="POST",
                headers={**HEADERS, "Content-Type": "application/json"},
                body=json.dumps({"descripcion": termino, "idcliente": 0}),
                # 404 es "sin resultados", no un error.
                meta={"handle_httpstatus_list": [404]},
                # Mismo URL para todos los términos: el dupefilter los
                # descartaría.
                dont_filter=True,
                callback=self.parse, cb_kwargs={"clave": clave})

    def parse(self, response, clave: str):
        """Una categoría o una búsqueda completa: no hay páginas."""
        if response.status == 404:
            productos = []
        else:
            try:
                productos = response.json()
            except ValueError:
                productos = None
        if not isinstance(productos, list):
            # 200 con XML o HTML: se pide otra vez; si se agotan los
            # reintentos, la partición queda en sin_datos.
            self.logger.warning("Respuesta sin lista de productos",
                                extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/paginas_sin_datos")
            otra = get_retry_request(response.request, spider=self,
                                     reason="pagina_incompleta")
            if otra is not None:
                yield otra
            return
        self.sin_datos.discard(clave)
        self.total_reportado = (self.total_reportado or 0) + len(productos)
        skus = {p["codigoBarras"] for p in productos}
        self.por_categoria[clave] = {"total_reportado": len(productos),
                                     "skus": skus}
        if clave.startswith("busqueda:") and len(productos) >= TOPE_BUSQUEDA:
            self.logger.warning("Búsqueda en el tope de %s: puede faltar "
                                "parte; partirla con otra palabra",
                                TOPE_BUSQUEDA, extra={"url": clave})
            self.crawler.stats.inc_value(f"{self.name}/busquedas_en_tope")

        ahora = datetime.now(timezone.utc)
        for producto in productos:
            fila = self.fila(producto, ahora, response.url)
            if fila["precio_lista"] is None:
                self.crawler.stats.inc_value(f"{self.name}/sin_precio")
                continue
            yield fila

    def fila(self, producto: dict, ahora: datetime, url_fuente: str) -> dict:
        # categorias/{id} y productos/busqueda nombran distinto los mismos
        # datos; los precios coinciden entre los dos (reconocimiento).
        if "precioOriginal" in producto:
            lista = precio(producto.get("precioOriginal"))
            venta = precio(producto.get("precioPublico"))
            nombre = producto["descripcionCorta"]
        else:
            lista = precio(producto.get("precioVenta"))
            venta = precio(producto.get("precioFinal"))
            nombre = producto["descripcion"]
        # Sin descuento real, un solo precio en precio_lista (contrato v1).
        if venta is None:
            lista = None
        elif lista is None or venta >= lista:
            lista, venta = venta, None
        codigo = producto["codigoBarras"].strip()
        atributos = {"principio_activo": producto.get("componenteActivo"),
                     "id_categoria": producto.get("idCategoria")}
        return {
            "capturado_en": ahora,
            "url_producto": f"{SITIO}/producto/{codigo}",
            "sku_tienda": codigo,
            "producto": " ".join(nombre.split()),
            "marca": None,
            # codigoBarras es el EAN salvo unos pocos códigos internos cortos.
            "ean": codigo if codigo.isdigit() and len(codigo) >= 8 else None,
            "categoria_ruta": None,
            "precio_lista": lista,
            "precio_oferta": venta,
            "moneda": "MXN",
            # existencia viene en 0 y disponibilidad en ALTA en todos.
            "disponible": None,
            "url_imagen": None,
            "zona_precio": ZONA,
            "url_fuente": url_fuente,
            "atributos_tienda": {k: str(v) for k, v in atributos.items()
                                 if v not in (None, "")},
        }


def precio(valor) -> Decimal | None:
    """Decimal del precio; None si falta o es 0."""
    return Decimal(str(valor)) if valor else None
