"""Pruebas de bloqueo, backoff y proxy con respuestas simuladas."""
import json

import pytest
from curl_cffi.requests.exceptions import RequestException, Timeout
from scrapy import Request
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import HtmlResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.middlewares.backoff import Backoff
from precios_scrapers.middlewares.bloqueo import Bloqueo
from precios_scrapers import settings as proyecto
from precios_scrapers.middlewares.proxy import Proxy
from precios_scrapers.pipelines.parquet import PipelineParquet
from precios_scrapers.spiders.prueba import SpiderPrueba

URL = "https://tienda.mx/farmacia?start=0&sz=96"


def crawler_de_prueba(tmp_path=None, **extra):
    # Solo los settings del proyecto que usan los middlewares: con todos,
    # Scrapy exige un reactor instalado.
    settings = {clave: getattr(proyecto, clave) for clave in (
        "RETRY_TIMES", "BLOQUEO_SEGUIDOS", "BLOQUEO_PAUSA_LARGA",
        "PARQUET_FILAS_POR_PARTE")}
    settings.update({"AXIOM_ENTORNO": "oficina",
                     "AXIOM_DESTINO": str(tmp_path or "."), **extra})
    crawler = get_crawler(SpiderPrueba, settings)
    crawler.spider = SpiderPrueba.from_crawler(crawler)
    return crawler


class Registro:
    """Sustituye pausar() y cerrar() para ver qué decidió el middleware."""

    def __init__(self, mw) -> None:
        self.pausas, self.cierres = [], []
        mw.pausar = lambda segundos, url: self.pausas.append(segundos)
        if hasattr(mw, "cerrar"):
            mw.cerrar = self.cierres.append


@pytest.fixture
def bloqueo():
    mw = Bloqueo.from_crawler(crawler_de_prueba())
    return mw, Registro(mw)


@pytest.fixture
def backoff():
    mw = Backoff.from_crawler(crawler_de_prueba())
    return mw, Registro(mw)


def respuesta(status=200, cuerpo=b"<html>ok</html>", headers=None,
              request=None):
    request = request or Request(URL)
    return HtmlResponse(URL, status=status, body=cuerpo, headers=headers,
                        request=request)


@pytest.mark.parametrize("status, cuerpo, motivo", [
    (403, b"<html>Please verify you are human</html>", "status_403"),
    (200, b"<html><iframe>Incapsula incident ID: 1</iframe></html>",
     "firma_incapsula"),
    (468, b"", "status_468"),
    (429, b"<div id='px-captcha'></div>", "firma_captcha"),
])
def test_bloqueos_se_reprograman_con_espera(bloqueo, status, cuerpo, motivo):
    mw, registro = bloqueo
    request = Request(URL)
    resultado = mw.process_response(request, respuesta(status, cuerpo,
                                                       request=request))
    assert isinstance(resultado, Request) and resultado.url == URL
    assert resultado.dont_filter
    assert registro.pausas == [30]
    stats = mw.crawler.stats.get_stats()
    assert stats["bloqueos"] == 1 and stats[f"bloqueos/{motivo}"] == 1


def test_redirect_a_portada_es_bloqueo(bloqueo):
    mw, _ = bloqueo
    request = Request("https://tienda.mx/",
                      meta={"redirect_urls": [URL]})
    final = HtmlResponse("https://tienda.mx/", body=b"<html></html>",
                         request=request)
    assert isinstance(mw.process_response(request, final), Request)


def test_recaptcha_en_la_csp_no_es_bloqueo(bloqueo):
    mw, registro = bloqueo
    csp = (b'<meta http-equiv="Content-Security-Policy" '
           b'content="script-src www.google.com www.recaptcha.net">')
    r = respuesta(cuerpo=csp)
    assert mw.process_response(r.request, r) is r
    assert registro.pausas == []


@pytest.mark.parametrize("status, headers", [
    (404, None), (503, None), (429, {"Retry-After": "90"}), (200, None)])
def test_lo_que_no_es_bloqueo_pasa(bloqueo, status, headers):
    mw, registro = bloqueo
    r = respuesta(status, headers=headers)
    assert mw.process_response(r.request, r) is r
    assert registro.pausas == []


def test_reset_es_bloqueo_y_timeout_no(bloqueo):
    mw, registro = bloqueo
    reset = RequestException("curl: (92) HTTP/2 stream 1 reset by server")
    assert isinstance(mw.process_exception(Request(URL), reset), Request)
    assert mw.process_exception(Request(URL), Timeout("timeout")) is None
    assert registro.pausas == [30]


def test_esperas_crecen_y_un_exito_reinicia(bloqueo):
    mw, registro = bloqueo
    for _ in range(4):
        r = respuesta(403)
        mw.process_response(r.request, r)
    ok = respuesta()
    mw.process_response(ok.request, ok)
    r = respuesta(403)
    mw.process_response(r.request, r)
    assert registro.pausas == [30, 60, 120, 120, 30]


def test_circuit_breaker_pausa_y_luego_cierra(bloqueo):
    mw, registro = bloqueo
    for _ in range(10):
        r = respuesta(403)
        mw.process_response(r.request, r)
    assert registro.pausas[-1] == 1800 and registro.cierres == []
    for _ in range(9):
        r = respuesta(403)
        mw.process_response(r.request, r)
    r = respuesta(403)
    with pytest.raises(IgnoreRequest):
        mw.process_response(r.request, r)
    assert registro.cierres == ["bloqueo_sostenido"]
    assert registro.pausas.count(1800) == 1


def test_backoff_5xx_espera_30_60_120_y_se_rinde(backoff):
    mw, registro = backoff
    request = Request(URL)
    for _ in range(3):
        request = mw.process_response(request, respuesta(503,
                                                         request=request))
        assert isinstance(request, Request)
    final = respuesta(503, request=request)
    assert mw.process_response(request, final) is final
    assert registro.pausas == [30, 60, 120]
    assert mw.crawler.stats.get_value("retry/count") == 3


@pytest.mark.parametrize("valor, espera", [
    ("90", 90), ("5", 30), ("99999", 1800),
    ("Wed, 21 Oct 2015 07:28:00 GMT", 30)])
def test_backoff_429_respeta_retry_after(backoff, valor, espera):
    mw, registro = backoff
    r = respuesta(429, headers={"Retry-After": valor})
    assert isinstance(mw.process_response(r.request, r), Request)
    assert registro.pausas == [espera]


def test_backoff_no_toca_404(backoff):
    mw, registro = backoff
    r = respuesta(404)
    assert mw.process_response(r.request, r) is r
    assert registro.pausas == []


def test_backoff_reintenta_timeout(backoff):
    mw, registro = backoff
    assert isinstance(mw.process_exception(Request(URL), Timeout("t")),
                      Request)
    assert registro.pausas == [30]


def test_proxy_apagado_y_encendido():
    with pytest.raises(NotConfigured):
        Proxy.from_crawler(crawler_de_prueba(PROXY_URL=""))
    mw = Proxy.from_crawler(crawler_de_prueba(PROXY_URL="http://p:8080"))
    request = Request(URL)
    mw.process_request(request)
    assert request.meta["proxy"] == "http://p:8080"


def test_corrida_json_lleva_bloqueos_reintentos_y_razon(tmp_path):
    crawler = crawler_de_prueba(tmp_path)
    crawler.stats.set_value("bloqueos", 20)
    crawler.stats.set_value("retry/count", 3)
    pipeline = PipelineParquet.from_crawler(crawler)
    pipeline.open_spider()
    pipeline.cerrar(crawler.spider, reason="bloqueo_sostenido")
    with open(f"{pipeline.carpeta}/_corrida.json", encoding="utf-8") as f:
        corrida = json.load(f)
    assert corrida["estado"] == "abortada"
    assert corrida["razon_cierre"] == "bloqueo_sostenido"
    assert (corrida["bloqueos"], corrida["reintentos"]) == (20, 3)
