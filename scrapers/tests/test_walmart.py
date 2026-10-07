"""Pruebas offline del spider de Walmart con páginas reales recortadas.

Los fixtures salen de las sondas de ALD-121 (2026-10-07, sucursal 3864) con
``fixtures/walmart/recortar.py``.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from scrapy import Request
from scrapy.exceptions import CloseSpider
from scrapy.http import HtmlResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.walmart import SpiderWalmart

FIXTURES = Path(__file__).parent / "fixtures" / "walmart"
MEDICAMENTOS = ("https://www.walmart.com.mx/browse/farmacia-y-cuidado-de-la-"
                "salud/medicamentos")
ANALGESICOS = f"{MEDICAMENTOS}/analgesicos/264536_1310112_2410125"
ALTA = f"{MEDICAMENTOS}/alta-especialidad/264536_1310112_120504"
RUTA = ["Farmacia y Cuidado de la Salud", "Medicamentos", "Analgésicos"]


@pytest.fixture
def spider():
    crawler = get_crawler(SpiderWalmart, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderWalmart.from_crawler(crawler)
    return crawler.spider


def respuesta(fixture: str, url: str) -> HtmlResponse:
    cuerpo = (FIXTURES / f"{fixture}.html").read_bytes()
    return HtmlResponse(url, body=cuerpo, request=Request(url))


def separar(salida) -> tuple[list[dict], list[Request]]:
    salida = list(salida)
    return ([x for x in salida if isinstance(x, dict)],
            [x for x in salida if isinstance(x, Request)])


def parametros(request: Request) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(request.url).query).items()}


def test_rama_pide_sus_25_hojas(spider):
    filas, peticiones = separar(spider.parse_rama(
        respuesta("rama_medicamentos", f"{MEDICAMENTOS}/264536_1310112")))
    assert not filas
    assert len(peticiones) == 25
    assert spider.total_reportado == 2384
    assert spider.sucursal == "3864"
    alta = peticiones[0]
    assert alta.url.endswith("/264536_1310112_120504")
    assert alta.cb_kwargs["ruta"] == ["Farmacia y Cuidado de la Salud",
                                      "Medicamentos", "Alta Especialidad"]


def test_hoja_chica_pagina_hasta_max_page(spider):
    filas, peticiones = separar(spider.parse_listado(
        respuesta("analgesicos_p1", ANALGESICOS), hoja="h", ruta=RUTA))
    assert len(filas) == 40
    assert [parametros(p) for p in peticiones] == [{"page": "2"}]
    assert spider.por_categoria["h"]["total_reportado"] == 75
    assert len(spider.por_categoria["h"]["skus"]) == 40

    filas, peticiones = separar(spider.parse_listado(
        respuesta("analgesicos_p2", f"{ANALGESICOS}?page=2"), hoja="h",
        ruta=RUTA, pagina=2))
    assert len(filas) == 31 and not peticiones
    assert len(spider.por_categoria["h"]["skus"]) == 71


def test_filas_cumplen_el_contrato(spider):
    filas, _ = separar(spider.parse_listado(
        respuesta("analgesicos_p1", ANALGESICOS), hoja="h", ruta=RUTA))
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "walmart",
                    "escalon": "d"}
        assert validar(completa, "walmart") is None, fila["sku_tienda"]
    fila = filas[0]
    assert fila["zona_precio"] == "3864"
    assert fila["ean"] == fila["sku_tienda"]
    assert fila["url_producto"].startswith("https://www.walmart.com.mx/ip/")
    assert fila["categoria_ruta"] == RUTA


def test_precio_tachado_va_como_lista(spider):
    filas, _ = separar(spider.parse_listado(
        respuesta("hoja_alta_especialidad", ALTA), hoja="h", ruta=RUTA))
    con_descuento = [f for f in filas if f["precio_oferta"] is not None]
    assert con_descuento
    for fila in con_descuento:
        assert fila["precio_oferta"] < fila["precio_lista"]


def test_hoja_sobre_el_tope_se_parte_por_precio(spider):
    # 1,607 productos no caben en 23 páginas de 40.
    filas, peticiones = separar(spider.parse_listado(
        respuesta("hoja_alta_especialidad", ALTA), hoja="h", ruta=RUTA))
    assert len(filas) == 40
    assert [parametros(p) for p in peticiones] == [
        {"min_price": "0", "max_price": "13428"}, {"min_price": "13428"}]
    assert peticiones[1].cb_kwargs["techo"] == 26856


def test_segmento_que_cabe_pagina_con_su_filtro(spider):
    url = f"{ALTA}?min_price=500"
    _, peticiones = separar(spider.parse_listado(
        respuesta("segmento_desde_500", url), hoja="h", ruta=RUTA,
        segmento=(500, None), techo=26856))
    assert len(peticiones) == 19
    assert parametros(peticiones[-1]) == {"min_price": "500", "page": "20"}
    assert peticiones[-1].cb_kwargs["segmento"] == (500, None)


def test_segmento_vacio_no_pide_nada(spider):
    # Sin medicamentos de ese precio: total 0 y maxPage 0, sin desafío.
    url = (f"{MEDICAMENTOS}/otros-medicamentos/264536_1310112_2470029"
           "?min_price=6714&max_price=13428")
    assert list(spider.parse_listado(
        respuesta("segmento_vacio", url), hoja="h", ruta=RUTA,
        segmento=(6714, 13428), techo=26856)) == []


def test_partir_se_detiene_en_un_peso():
    assert SpiderWalmart.partir((10, 11), None) is None
    assert SpiderWalmart.partir((0, None), None) is None
    assert SpiderWalmart.partir((0, None), 100) == [(0, 50), (50, None)]


def test_sucursal_distinta_cierra_la_corrida(spider):
    spider.sucursal = "2344"
    with pytest.raises(CloseSpider) as cierre:
        list(spider.parse_listado(respuesta("analgesicos_p1", ANALGESICOS),
                                  hoja="h", ruta=RUTA))
    assert cierre.value.reason == "sucursal_cambiada"


def test_pagina_sin_datos_no_rompe(spider):
    vacia = HtmlResponse(ANALGESICOS, body=b"<html></html>",
                         request=Request(ANALGESICOS))
    assert list(spider.parse_listado(vacia, hoja="h", ruta=RUTA)) == []
    assert spider.crawler.stats.get_value("walmart/paginas_sin_datos") == 1
