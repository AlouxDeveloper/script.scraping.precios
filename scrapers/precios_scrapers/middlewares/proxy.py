"""Punto de integración del proxy (ADR-07), apagado por defecto.

Con ``PROXY_URL`` vacía no hace nada. Con valor, pone ``request.meta["proxy"]``,
que leen ``HttpProxyMiddleware`` de Scrapy y scrapy-impersonate. El navegador
(escalones c y d) no pasa por aquí: su proxy va en el lanzamiento o contexto.
"""
from scrapy.exceptions import NotConfigured


class Proxy:
    """Downloader middleware; va antes de HttpProxyMiddleware (750)."""

    def __init__(self, url: str) -> None:
        self.url = url

    @classmethod
    def from_crawler(cls, crawler):
        url = crawler.settings.get("PROXY_URL")
        if not url:
            raise NotConfigured
        return cls(url)

    def process_request(self, request):
        request.meta.setdefault("proxy", self.url)
