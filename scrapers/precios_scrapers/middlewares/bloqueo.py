"""Clasifica bloqueos, los reprograma y corta la corrida si persisten.

Señales (Metodología, sección 4): 403 y 468; cualquier status con una firma
de WAF o de desafío en el cuerpo (incluye 200 con HTML de Imperva y 429 con
desafío); redirect que termina en la portada o en una ruta de CAPTCHA; y
conexión reseteada. 429 sin firma, 5xx y timeouts no son bloqueo: los toma
``Backoff``. 404 es normal (producto dado de baja) y pasa tal cual.

Un bloqueo nunca marca la URL como fallida: se reprograma tras una pausa
(30, 60, 120 s). Con ``BLOQUEO_SEGUIDOS`` bloqueos seguidos la corrida se
pausa ``BLOQUEO_PAUSA_LARGA`` segundos; si vuelve a pasar, cierra con razón
``bloqueo_sostenido``.
"""
import logging
from urllib.parse import urlparse

from curl_cffi.requests.exceptions import RequestException, Timeout
from scrapy.exceptions import DownloadTimeoutError, IgnoreRequest
from scrapy.utils.defer import deferred_from_coro
from twisted.internet.error import ConnectionDone, ConnectionLost

from precios_scrapers.middlewares.backoff import ESPERAS, pausar
from precios_scrapers.spiders.base import cargar_tienda

# Firmas de la Metodología, sección 4. Se buscan en los primeros 5,000
# bytes, igual que validar_endpoint.py; cada tienda suma las suyas.
FIRMAS = ("captcha", "incapsula", "access denied", "_pxhd", "cf-chl")
STATUS_BLOQUEO = {403, 468}
RUTAS_BLOQUEO = ("captcha", "blocked", "challenge")
TIMEOUTS = (Timeout, DownloadTimeoutError)
# Akamai corta con "HTTP/2 stream reset" (curl 92) cuando no le gusta la
# huella o el ritmo; curl_cffi lo lanza como RequestException genérica.
RESETS = (RequestException, ConnectionLost, ConnectionDone)

logger = logging.getLogger(__name__)


class Bloqueo:
    """Downloader middleware; va antes de Backoff y después de Redirect."""

    def __init__(self, crawler) -> None:
        self.crawler = crawler
        tienda = cargar_tienda(crawler.spidercls.name)
        self.firmas = [f.encode() for f in
                       (*FIRMAS, *tienda.get("firmas_bloqueo", []))]
        self.umbral = crawler.settings.getint("BLOQUEO_SEGUIDOS")
        self.pausa_larga = crawler.settings.getint("BLOQUEO_PAUSA_LARGA")
        self.seguidos = 0
        self.pausas_largas = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def motivo(self, request, response) -> str | None:
        """Devuelve por qué la respuesta es bloqueo, o None si no lo es."""
        if response.status in STATUS_BLOQUEO:
            return f"status_{response.status}"
        # Walmart lista www.recaptcha.net en la CSP del <head> de toda página;
        # en una página sin productos cae dentro de los 5,000 bytes y la
        # firma "captcha" la tomaba por desafío (ALD-121). Nombrar el host no
        # es un desafío.
        cuerpo = response.body[:5000].lower().replace(b"recaptcha.net", b"")
        firma = next((f for f in self.firmas if f in cuerpo), None)
        if firma:
            return f"firma_{firma.decode()}"
        # Con navegador el redirect ocurre dentro de Chrome: no deja
        # redirect_urls, solo una URL final distinta.
        if request.meta.get("redirect_urls") or response.url != request.url:
            ruta = urlparse(response.url).path.lower()
            if ruta in ("", "/") or any(r in ruta for r in RUTAS_BLOQUEO):
                return "redirect"
        return None

    def process_response(self, request, response):
        motivo = self.motivo(request, response)
        if motivo is None:
            self.seguidos = 0
            return response
        return self.bloqueo(request, motivo)

    def process_exception(self, request, exception):
        if isinstance(exception, TIMEOUTS) or not isinstance(exception, RESETS):
            return None
        return self.bloqueo(request, "reset")

    def bloqueo(self, request, motivo: str):
        stats = self.crawler.stats
        stats.inc_value("bloqueos")
        stats.inc_value(f"bloqueos/{motivo}")
        self.seguidos += 1
        logger.warning("Bloqueo (%s), %s seguidos", motivo, self.seguidos,
                       extra={"url": request.url})
        if self.seguidos >= self.umbral:
            self.seguidos = 0
            if self.pausas_largas:
                self.cerrar("bloqueo_sostenido")
                raise IgnoreRequest("bloqueo_sostenido")
            self.pausas_largas += 1
            self.pausar(self.pausa_larga, request.url)
        else:
            self.pausar(ESPERAS[min(self.seguidos, len(ESPERAS)) - 1],
                        request.url)
        # dont_filter: el dupefilter ya vio esta URL y la descartaría.
        # axiom_bloqueo: el escalón d cuenta bloqueos por contexto.
        reintento = request.replace(dont_filter=True)
        reintento.meta["axiom_bloqueo"] = motivo
        return reintento

    def pausar(self, segundos: float, url: str) -> None:
        pausar(self.crawler, segundos, url)

    def cerrar(self, razon: str) -> None:
        logger.error("Corrida cerrada por %s", razon)
        deferred_from_coro(self.crawler.engine.close_spider_async(reason=razon))
