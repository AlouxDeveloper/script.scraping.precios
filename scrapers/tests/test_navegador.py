"""Pruebas del escalón d con páginas de Playwright simuladas (sin navegador)."""
import asyncio

from scrapy import Request
from scrapy.http import HtmlResponse
from scrapy.utils.test import get_crawler

from precios_scrapers import navegador
from precios_scrapers.middlewares.bloqueo import Bloqueo
from precios_scrapers.spiders.base import SpiderTienda

URL = "https://www.walmart.com.mx/browse/medicamentos/264536_1310112?page=2"


class SpiderD(SpiderTienda):
    name = "walmart"


class Contexto:
    def __init__(self) -> None:
        self.cerrado = False

    async def close(self) -> None:
        self.cerrado = True


class Pagina:
    def __init__(self, contexto: Contexto) -> None:
        self.context = contexto
        self.cerrada = False

    async def unroute_all(self, behavior: str) -> None:
        pass

    async def close(self) -> None:
        self.cerrada = True


def crawler_d(**extra):
    return get_crawler(SpiderD, {"AXIOM_ENTORNO": "oficina",
                                 "NAVEGADOR_BLOQUEOS_POR_CONTEXTO": 2,
                                 "BLOQUEO_SEGUIDOS": 10, **extra})


def descargar(mw, contexto: Contexto, request=None) -> Pagina:
    """Simula el viaje de una petición por el middleware y el handler."""
    request = request or Request(URL)
    asyncio.run(mw.process_request(request))
    assert request.meta["playwright"] and request.meta["playwright_include_page"]
    pagina = Pagina(contexto)
    request.meta["playwright_page"] = pagina
    respuesta = HtmlResponse(URL, body=b"<html></html>", request=request)
    asyncio.run(mw.process_response(request, respuesta))
    assert pagina.cerrada and "playwright_page" not in request.meta
    return pagina


def test_escalon_d_usa_playwright_con_patchright():
    settings = crawler_d().settings
    assert settings.getdict("DOWNLOAD_HANDLERS")["https"] == navegador.HANDLER
    assert settings["PLAYWRIGHT_BROWSER_PROVIDER"].endswith("ProviderPatchright")
    assert settings.getdict("PLAYWRIGHT_LAUNCH_OPTIONS")["channel"] == "chrome"


def test_un_contexto_para_toda_la_corrida():
    mw = navegador.ContextoNavegador.from_crawler(crawler_d())
    contexto = Contexto()
    for _ in range(20):
        descargar(mw, contexto)
    assert not contexto.cerrado


def test_segundo_bloqueo_seguido_descarta_el_contexto():
    crawler = crawler_d()
    crawler.spider = SpiderD.from_crawler(crawler)
    mw = navegador.ContextoNavegador.from_crawler(crawler)
    bloqueo = Bloqueo.from_crawler(crawler)
    bloqueo.pausar = lambda segundos, url: None
    contexto = Contexto()
    descargar(mw, contexto)

    def bloquear():
        # Chrome sigue el redirect por dentro: solo cambia la URL final.
        request = Request(URL)
        desafio = HtmlResponse("https://www.walmart.com.mx/blocked",
                               body=b"<html></html>", request=request)
        reintento = bloqueo.process_response(request, desafio)
        assert reintento.meta["axiom_bloqueo"] == "redirect"
        return reintento

    # El primero es el desafío inicial de la sesión: se reintenta igual.
    descargar(mw, contexto, bloquear())
    assert not contexto.cerrado
    descargar(mw, Contexto(), bloquear())
    assert contexto.cerrado

    # Una página buena en medio reinicia la cuenta.
    otro = Contexto()
    descargar(mw, otro, bloquear())
    descargar(mw, otro)
    descargar(mw, otro, bloquear())
    assert not otro.cerrado
    assert crawler.stats.get_value("navegador/contextos_descartados") == 1
