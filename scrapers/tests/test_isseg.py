"""Pruebas offline del spider de ISSEG con las muestras del reconocimiento.

Fixtures de ``reconocimiento/isseg/muestras`` (2026-10-15), con la imagen
base64 ya recortada: 2 productos de ``categorias/1``, 2 de la búsqueda
``losartan`` (con descuento) y la página de CAPTCHA de SafeLine que llega con
el HTTP 468.
"""
import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse, TextResponse
from scrapy.utils.test import get_crawler

from precios_scrapers import settings as proyecto
from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.middlewares.bloqueo import Bloqueo
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.isseg import API, SpiderIsseg

FIXTURES = Path(__file__).parent / "fixtures" / "isseg"
CATEGORIA = f"{API}/categorias/1"
BUSQUEDA = f"{API}/productos/busqueda"


@pytest.fixture
def spider():
    # Los settings de bloqueo del proyecto, que usa el caso del 468.
    settings = {clave: getattr(proyecto, clave) for clave in (
        "RETRY_TIMES", "BLOQUEO_SEGUIDOS", "BLOQUEO_PAUSA_LARGA")}
    crawler = get_crawler(SpiderIsseg, {**settings,
                                        "AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderIsseg.from_crawler(crawler)
    return crawler.spider


def respuesta(url: str, cuerpo: bytes, status: int = 200) -> TextResponse:
    return TextResponse(url, status=status, body=cuerpo, encoding="utf-8",
                        request=Request(url))


def fixture(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


def peticiones(spider) -> list[Request]:
    async def juntar():
        return [r async for r in spider.start()]
    return asyncio.run(juntar())


def test_start_pide_categorias_y_busquedas_con_referer(spider):
    salida = peticiones(spider)
    categoria, *busquedas = salida
    assert categoria.url == CATEGORIA
    assert len(busquedas) == len(spider.tienda["busquedas"])
    for peticion in salida:
        assert peticion.headers["Referer"] == b"https://farmaciasisseg.com.mx/"
        assert peticion.headers["Accept"] == b"application/json"
    primera = busquedas[0]
    assert primera.method == "POST" and primera.dont_filter
    assert json.loads(primera.body) == {"descripcion": "paracetamol",
                                        "idcliente": 0}
    assert 404 in primera.meta["handle_httpstatus_list"]
    assert spider.sin_datos == {"categoria:1", *(
        f"busqueda:{t}" for t in spider.tienda["busquedas"])}


def test_categoria_y_busqueda_cumplen_el_contrato(spider):
    filas = [
        *spider.parse(respuesta(CATEGORIA, fixture("categorias_1_2.json")),
                      clave="categoria:1"),
        *spider.parse(respuesta(BUSQUEDA,
                                fixture("busqueda_losartan_2.json")),
                      clave="busqueda:losartan")]
    assert len(filas) == 4
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "isseg",
                    "escalon": "b"}
        assert validar(completa, "isseg") is None, fila["sku_tienda"]
        # La imagen viene en base64: nunca se guarda.
        assert fila["url_imagen"] is None
    alercrom, _, losartan, _ = filas
    assert alercrom["sku_tienda"] == "008400000248"
    assert alercrom["url_producto"] == (
        "https://farmaciasisseg.com.mx/producto/008400000248")
    assert (alercrom["precio_lista"], alercrom["precio_oferta"]) == (
        Decimal("411.0"), None)
    assert alercrom["atributos_tienda"] == {"id_categoria": "1"}
    assert (losartan["precio_lista"], losartan["precio_oferta"]) == (
        Decimal("1545.0"), Decimal("1420.0"))
    assert "principio_activo" in losartan["atributos_tienda"]
    assert spider.por_categoria["busqueda:losartan"]["total_reportado"] == 2
    assert not spider.sin_datos & {"categoria:1", "busqueda:losartan"}


def test_busqueda_sin_resultados_es_404_vacio(spider):
    spider.sin_datos.add("busqueda:zzq")
    assert not list(spider.parse(respuesta(BUSQUEDA, b"", 404),
                                 clave="busqueda:zzq"))
    assert "busqueda:zzq" not in spider.sin_datos
    assert spider.por_categoria["busqueda:zzq"]["total_reportado"] == 0


def test_busqueda_en_el_tope_queda_marcada(spider):
    producto = json.loads(fixture("busqueda_losartan_2.json"))[0]
    cien = [{**producto, "codigoBarras": str(n)} for n in range(100)]
    list(spider.parse(respuesta(BUSQUEDA, json.dumps(cien).encode()),
                      clave="busqueda:metformina"))
    assert spider.crawler.stats.get_value("isseg/busquedas_en_tope") == 1


def test_respuesta_xml_se_pide_otra_vez(spider):
    [otra] = spider.parse(respuesta(CATEGORIA, b"<ArrayOfCategoriaDTO/>"),
                          clave="categoria:1")
    assert otra.dont_filter
    assert spider.crawler.stats.get_value("isseg/paginas_sin_datos") == 1


def test_468_de_safeline_es_bloqueo_y_se_reprograma(spider):
    mw = Bloqueo.from_crawler(spider.crawler)
    pausas = []
    mw.pausar = lambda segundos, url: pausas.append(segundos)
    request = Request(CATEGORIA)
    pagina = fixture("waf_468_safeline.html")
    otra = mw.process_response(request, HtmlResponse(
        CATEGORIA, status=468, body=pagina, request=request))
    assert isinstance(otra, Request) and otra.dont_filter
    assert otra.meta["axiom_bloqueo"] == "status_468"
    assert pausas == [30]
    # La misma página con otro status la delata la firma de tiendas.yml.
    otra = mw.process_response(request, HtmlResponse(
        CATEGORIA, status=200, body=pagina, request=request))
    assert otra.meta["axiom_bloqueo"] == "firma_de seguridad isseg"
    assert spider.crawler.stats.get_value("bloqueos") == 2
