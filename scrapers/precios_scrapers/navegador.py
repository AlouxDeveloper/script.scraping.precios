"""Escalón d: navegador completo con scrapy-playwright y Patchright.

``SpiderTienda`` aplica ``SETTINGS`` a las tiendas con ``escalon: d``: todas
sus peticiones van por Chrome (Patchright, ADR-03 del PRD) y no por
curl_cffi. ``ContextoNavegador`` mantiene un solo contexto (una sesión) toda
la corrida y lo descarta solo si sigue bloqueado.

Medido contra Walmart (HUMAN) el 2026-10-07 desde la oficina: un contexto
largo pasó 20 páginas seguidas sin desafío; un contexto nuevo recibe el
desafío en su primera página y, en el mismo contexto, la siguiente ya pasa
(el sensor de HUMAN corre en la página del desafío y deja ``_px3``).
Renovar el contexto cada N páginas o en cada bloqueo, como proponía el
reconocimiento, encadena desafíos sin salida.

Los desafíos nunca se resuelven (Metodología): se tratan como bloqueo.
"""
import atexit
import logging
import sys
from contextlib import AsyncExitStack

from scrapy.exceptions import NotConfigured
from scrapy.settings.default_settings import RETRY_EXCEPTIONS

from precios_scrapers.spiders.base import cargar_tienda

HANDLER = "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"
SETTINGS = {
    "DOWNLOAD_HANDLERS": {"http": HANDLER, "https": HANDLER},
    "PLAYWRIGHT_BROWSER_PROVIDER": "precios_scrapers.navegador.ProviderPatchright",
    # Patchright solo es indetectable con Chrome real y ventana visible; con
    # Chromium o headless cambia la huella. En Linux sin Chrome se puede
    # probar con -s PLAYWRIGHT_LAUNCH_OPTIONS='{"headless": false}'.
    # TODO: el proxy (ADR-07) va aquí como {"proxy": {"server": ...}}; la
    # meta "proxy" del middleware Proxy no la lee Playwright.
    "PLAYWRIGHT_LAUNCH_OPTIONS": {"channel": "chrome", "headless": False},
    # Una petición a la vez en el downloader. Si no, el engine le pasa hasta
    # 16 juntas y ContextoNavegador las ve todas antes de la primera
    # respuesta: no sabría a qué contexto le tocó el bloqueo.
    "CONCURRENT_REQUESTS": 1,
    # Un fallo del navegador (página o contexto cerrado) se reintenta con
    # Backoff en lugar de perder la página.
    "RETRY_EXCEPTIONS": [*RETRY_EXCEPTIONS, "patchright.async_api.Error"],
}

logger = logging.getLogger(__name__)


class ProviderPatchright:
    """Arranca Chromium con Patchright en lugar de Playwright.

    Es el ejemplo de la documentación de scrapy-playwright
    (docs/pluggable-browser-providers.md). Patchright importa tarde para que
    los escalones a y b no lo necesiten cargado.
    """

    def __init__(self, config) -> None:
        self.config = config
        self.stack = AsyncExitStack()

    async def start(self) -> None:
        from patchright.async_api import async_playwright

        if sys.platform == "win32":
            atexit.register(cerrar_loop_windows)

        patchright = await self.stack.enter_async_context(async_playwright())
        self.browser_type = patchright.chromium

    async def launch_browser(self):
        return await self.browser_type.launch(**self.config.launch_options)

    async def launch_persistent_context(self, context_kwargs: dict):
        return await self.browser_type.launch_persistent_context(
            **context_kwargs)

    async def close(self) -> None:
        await self.stack.aclose()


def cerrar_loop_windows() -> None:
    """Cierra el loop en hilo que scrapy-playwright deja abierto en Windows.

    En Windows, scrapy-playwright corre Playwright en un ProactorEventLoop en
    otro hilo y al terminar lo detiene sin cerrarlo. Su proactor conserva
    operaciones de E/S ya terminadas (la última lectura del pipe del driver,
    el despertador de ``loop.stop``) cuyo paquete IOCP nunca llega, y el
    ``close()`` que dispara la recolección al salir las espera para siempre:
    1 de cada 3 corridas no terminaba (medido el 2026-10-07). Se descartan
    esas entradas antes de cerrar; con ello, 20 de 20 corridas terminaron.
    """
    from scrapy_playwright._loop import _ThreadedLoopAdapter

    loop = getattr(_ThreadedLoopAdapter, "_loop", None)
    if loop is None or loop.is_closed() or loop.is_running():
        return
    # ponytail: toca atributos privados de asyncio y scrapy-playwright;
    # quitarlo cuando CPython o scrapy-playwright cierren el loop bien.
    cache = loop._proactor._cache
    for clave, (futuro, *_) in list(cache.items()):
        if futuro.done():
            del cache[clave]
    loop.close()


class ContextoNavegador:
    """Manda cada petición al navegador y descarta el contexto atascado.

    Va en 800, antes que los demás en la vuelta: cierra la página de
    Playwright aunque ``Bloqueo`` (585) después reprograme la petición.
    ``Bloqueo`` marca el reintento con la meta ``axiom_bloqueo``; con
    ``NAVEGADOR_BLOQUEOS_POR_CONTEXTO`` bloqueos seguidos en el mismo
    contexto, aquí se cierra antes de reenviar. Al cerrarse, scrapy-playwright
    lo olvida y la siguiente petición abre uno nuevo con el mismo nombre.
    """

    def __init__(self, crawler) -> None:
        if cargar_tienda(crawler.spidercls.name)["escalon"] != "d":
            raise NotConfigured("solo escalón d")
        self.crawler = crawler
        self.tope = crawler.settings.getint("NAVEGADOR_BLOQUEOS_POR_CONTEXTO")
        self.bloqueos = 0
        self.contexto = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_request(self, request):
        # Con una petición a la vez, una sin la marca significa que la
        # anterior no fue bloqueo.
        if not request.meta.pop("axiom_bloqueo", None):
            self.bloqueos = 0
        else:
            self.bloqueos += 1
            if self.bloqueos >= self.tope:
                await self.descartar()
        request.meta["playwright"] = True
        request.meta["playwright_include_page"] = True
        # Patchright pide no fijar viewport: el tamaño por defecto de
        # Playwright (1280x720) delata la automatización.
        request.meta.setdefault("playwright_context_kwargs",
                                {"no_viewport": True})

    async def process_response(self, request, response):
        pagina = request.meta.pop("playwright_page", None)
        if pagina is not None:
            self.contexto = pagina.context
            # Sin unroute_all, los callbacks de ruta de scrapy-playwright que
            # siguen en vuelo hacen fallar el new_page de la siguiente
            # petición con TargetClosedError (3 de 25 páginas en la sonda).
            await pagina.unroute_all(behavior="ignoreErrors")
            await pagina.close()
        return response

    async def descartar(self) -> None:
        if self.contexto is not None:
            await self.contexto.close()
            self.crawler.stats.inc_value("navegador/contextos_descartados")
            logger.warning("Contexto del navegador descartado tras %s "
                           "bloqueos seguidos", self.bloqueos)
        self.contexto = None
        self.bloqueos = 0
