"""Spider de prueba de la base: una petición impersonada y filas sintéticas.

Hace una sola petición real y, si se le pide, genera ``filas`` ítems
sintéticos para ejercitar el contrato y el pipeline Parquet sin más tráfico.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl prueba
    uv run --project scrapers scrapy crawl prueba -a filas=4500
    uv run --project scrapers scrapy crawl prueba -a url=https://httpbin.org/status/403
"""
from datetime import datetime, timezone
from decimal import Decimal

from precios_scrapers.spiders.base import SpiderTienda


class SpiderPrueba(SpiderTienda):
    """Pide las URLs de ``categorias`` de su bloque en tiendas.yml."""

    name = "prueba"

    def __init__(self, *args, filas: int = 0, url: str | None = None,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # ``url`` sustituye las de tiendas.yml: sirve para simular un
        # bloqueo con una URL que responde 403 y probar las alertas.
        self.start_urls = [url] if url else self.tienda["categorias"]
        self.filas = int(filas)

    def parse(self, response):
        self.logger.info("Respuesta recibida",
                         extra={"url": response.url, "status": response.status})
        self.total_reportado = self.filas or None
        for i in range(self.filas):
            yield {
                "capturado_en": datetime.now(timezone.utc),
                "url_producto": f"https://prueba.invalid/p/{i}",
                "sku_tienda": str(i),
                "producto": f"Producto sintético {i}",
                "precio_lista": Decimal("100.00"),
                "moneda": "MXN",
                "url_fuente": response.url,
            }
