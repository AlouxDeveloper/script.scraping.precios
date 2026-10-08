"""Pruebas offline del spider de Guadalajara con páginas reales recortadas.

Fixtures de la sonda de ALD-125 (2026-10-08) sobre ``/farmacia/medicina``,
recortados con ``fixtures/guadalajara/recortar.py``: la primera página y la
última (``start=3552``, 23 productos).
"""
from decimal import Decimal
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.guadalajara import SpiderGuadalajara

FIXTURES = Path(__file__).parent / "fixtures" / "guadalajara"
MEDICINA = "https://www.farmaciasguadalajara.com/farmacia/medicina"


@pytest.fixture
def spider():
    crawler = get_crawler(SpiderGuadalajara, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderGuadalajara.from_crawler(crawler)
    return crawler.spider


def respuesta(fixture: str, url: str) -> HtmlResponse:
    cuerpo = (FIXTURES / f"{fixture}.html").read_bytes()
    return HtmlResponse(url, body=cuerpo, encoding="utf-8",
                        request=Request(url))


def separar(salida) -> tuple[list[dict], list[Request]]:
    salida = list(salida)
    return ([x for x in salida if isinstance(x, dict)],
            [x for x in salida if isinstance(x, Request)])


def test_primera_pagina_pide_las_demas(spider):
    filas, peticiones = separar(spider.parse(
        respuesta("medicina_p1", f"{MEDICINA}?start=0&sz=96"),
        categoria="/farmacia/medicina", inicio=0))
    # 3,575 productos en páginas de 96: 37 páginas más la primera.
    assert len(peticiones) == 37
    assert peticiones[0].url == f"{MEDICINA}?start=96&sz=96"
    assert peticiones[-1].url == f"{MEDICINA}?start=3552&sz=96"
    assert spider.total_reportado == 3575
    assert len(spider.por_categoria["/farmacia/medicina"]["skus"]) == len(filas)


def test_filas_cumplen_el_contrato(spider):
    filas, _ = separar(spider.parse(
        respuesta("medicina_p1", f"{MEDICINA}?start=0&sz=96"),
        categoria="/farmacia/medicina", inicio=0))
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "guadalajara",
                    "escalon": "b"}
        assert validar(completa, "guadalajara") is None, fila["sku_tienda"]
    fila = filas[0]
    assert fila["sku_tienda"] == "1006290"
    assert fila["producto"] == "Seroquel 100 mg, 30 Tabletas."
    assert fila["url_producto"].endswith("-1006290.html")
    assert fila["precio_oferta"] == Decimal("1458.00")
    assert fila["precio_lista"] > fila["precio_oferta"]
    assert fila["categoria_ruta"] == ["Farmacia", "Medicina"]
    assert fila["zona_precio"] == "sin_ubicacion"
    assert "?" not in fila["url_imagen"]
    assert any(f["atributos_tienda"].get("promocion") for f in filas)


def test_ultima_pagina_no_pide_mas_y_tolera_sin_marca(spider):
    spider.por_categoria["/farmacia/medicina"] = {"total_reportado": 3575,
                                                  "skus": set()}
    filas, peticiones = separar(spider.parse(
        respuesta("medicina_ultima", f"{MEDICINA}?start=3552&sz=96"),
        categoria="/farmacia/medicina", inicio=3552))
    assert not peticiones
    assert any(f["marca"] is None for f in filas)


def test_pagina_sin_total_se_pide_otra_vez(spider):
    url = f"{MEDICINA}?start=0&sz=96"
    vacia = HtmlResponse(url, body=b"<html></html>", request=Request(url))
    [otra] = spider.parse(vacia, categoria="/farmacia/medicina", inicio=0)
    assert otra.url == url and otra.dont_filter
    assert spider.crawler.stats.get_value(
        "guadalajara/paginas_sin_datos") == 1


def test_corre_sin_cookies():
    crawler = get_crawler(SpiderGuadalajara, {"AXIOM_ENTORNO": "oficina"})
    assert crawler.settings.getbool("COOKIES_ENABLED") is False
