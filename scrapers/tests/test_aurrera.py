"""Pruebas offline del spider de Aurrera con páginas reales recortadas.

La lógica es la de Walmart (``test_walmart.py``); aquí solo se prueba que
la misma plataforma con otro dominio y otra sucursal se recorre igual.
Fixtures de la sonda de ALD-123 (2026-10-08, sucursal 2769), recortados con
``fixtures/walmart/recortar.py``.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.aurrera import SpiderAurrera

FIXTURES = Path(__file__).parent / "fixtures" / "aurrera"
SITIO = "https://www.bodegaaurrera.com.mx"
MEDICAMENTOS = (f"{SITIO}/browse/farmacia-y-cuidado-de-la-salud/medicamentos/"
                "264536_1310112")
# La hoja no lleva el slug de la rama, a diferencia de Walmart.
UVWXY = (f"{SITIO}/browse/farmacia-y-cuidado-de-la-salud/u-v-w-x-y/"
         "264536_1310112_120470")
RUTA = ["Farmacia y Cuidado de la Salud", "Medicamentos", "U-V-W-X-Y"]


@pytest.fixture
def spider():
    crawler = get_crawler(SpiderAurrera, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderAurrera.from_crawler(crawler)
    return crawler.spider


def respuesta(fixture: str, url: str) -> HtmlResponse:
    cuerpo = (FIXTURES / f"{fixture}.html").read_bytes()
    return HtmlResponse(url, body=cuerpo, request=Request(url))


def test_rama_pide_sus_hojas_en_aurrera(spider):
    peticiones = list(spider.parse_rama(
        respuesta("rama_medicamentos", MEDICAMENTOS)))
    assert len(peticiones) == 25
    assert spider.total_reportado == 1951
    assert all(p.url.startswith(f"{SITIO}/browse/") for p in peticiones)
    assert UVWXY in [p.url for p in peticiones]


def test_hoja_se_parte_y_cumple_el_contrato(spider):
    salida = list(spider.parse_listado(respuesta("hoja_uvwxy", UVWXY),
                                       hoja="h", ruta=RUTA))
    filas = [x for x in salida if isinstance(x, dict)]
    peticiones = [x for x in salida if isinstance(x, Request)]
    # 60 productos y un anuncio: 40 orgánicos, corte en su mediana.
    assert len(filas) == 40
    assert [parse_qs(urlparse(p.url).query) for p in peticiones] == [
        {"min_price": ["0"], "max_price": ["687"]}, {"min_price": ["687"]}]
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "aurrera",
                    "escalon": "d"}
        assert validar(completa, "aurrera") is None, fila["sku_tienda"]
        assert fila["url_producto"].startswith(f"{SITIO}/ip/")
        assert fila["zona_precio"] == "2769"
