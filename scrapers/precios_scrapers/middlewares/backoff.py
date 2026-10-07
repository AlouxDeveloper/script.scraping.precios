"""Reintentos con espera exponencial y respeto de ``Retry-After``.

El ``RetryMiddleware`` de Scrapy reintenta 5xx, 408, 429 y errores de red,
pero reprograma de inmediato. Esta subclase conserva su lógica (y su stat
``retry/count``) y, antes de cada reintento, pausa la corrida 30, 60 o 120 s
según el número de intento, o lo que pida ``Retry-After`` si es más.
"""
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from scrapy import Request
from scrapy.downloadermiddlewares.retry import RetryMiddleware

ESPERAS = (30, 60, 120)
# Un Retry-After absurdo (horas) no debe congelar la corrida: el tope es la
# pausa larga del circuit breaker.
TOPE_RETRY_AFTER = 1800

logger = logging.getLogger(__name__)


def pausar(crawler, segundos: float, url: str | None = None) -> None:
    """Detiene el envío de peticiones nuevas durante ``segundos``.

    Pausa el engine y no solo la petición: con un sleep en el middleware el
    resto de la cola seguiría pegándole al sitio. Si ya hay una pausa más
    larga en curso, no la acorta.
    """
    # Import local: importar el reactor al cargar el módulo instalaría el
    # default antes de que Scrapy instale el de asyncio.
    from twisted.internet import reactor

    fin = time.monotonic() + segundos
    if fin <= getattr(crawler, "axiom_reanudar_en", 0):
        return
    crawler.axiom_reanudar_en = fin
    logger.warning("Pausa de %s s", segundos, extra={"url": url})
    crawler.engine.pause()

    def reanudar() -> None:
        # Una pausa posterior más larga movió el fin: esta no reanuda.
        if time.monotonic() >= crawler.axiom_reanudar_en - 0.5:
            crawler.engine.unpause()

    reactor.callLater(segundos, reanudar)


def segundos_retry_after(valor: bytes | None) -> float | None:
    """Interpreta Retry-After en segundos o como fecha HTTP."""
    if not valor:
        return None
    texto = valor.decode("latin-1").strip()
    if texto.isdigit():
        return float(texto)
    try:
        fecha = parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        return None
    return max((fecha - datetime.now(timezone.utc)).total_seconds(), 0)


class Backoff(RetryMiddleware):
    """RetryMiddleware que espera antes de reintentar."""

    def process_response(self, request, response):
        resultado = super().process_response(request, response)
        if isinstance(resultado, Request):
            self.esperar(resultado, response.headers.get("Retry-After"))
        return resultado

    def process_exception(self, request, exception):
        resultado = super().process_exception(request, exception)
        if isinstance(resultado, Request):
            self.esperar(resultado, None)
        return resultado

    def esperar(self, reintento: Request, retry_after: bytes | None) -> None:
        intento = reintento.meta["retry_times"]
        espera = ESPERAS[min(intento, len(ESPERAS)) - 1]
        pedida = segundos_retry_after(retry_after)
        if pedida is not None:
            espera = max(espera, min(pedida, TOPE_RETRY_AFTER))
        self.pausar(espera, reintento.url)

    def pausar(self, segundos: float, url: str) -> None:
        pausar(self.crawler, segundos, url)
