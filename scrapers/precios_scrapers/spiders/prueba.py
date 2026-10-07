"""Spider de prueba de la base: una petición impersonada y su status en log.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl prueba
"""
from precios_scrapers.spiders.base import SpiderTienda


class SpiderPrueba(SpiderTienda):
    """Pide las URLs de ``categorias`` de su bloque en tiendas.yml."""

    name = "prueba"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = self.tienda["categorias"]

    def parse(self, response):
        self.logger.info("Respuesta recibida",
                         extra={"url": response.url, "status": response.status})
