"""Pruebas offline del spider de San Pablo con respuestas OCC reales recortadas.

Fixtures de la búsqueda con ``fields=FULL`` (2026-10-15), recortados con
``fixtures/san_pablo/recortar.py``: la primera página de Medicamentos
(``06``, 5,419), de Supervisión médica (``06011``, 3,107) y de su
subcategoría A-B-C (``060110001``, 676), con sus facetas de códigos.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import TextResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.san_pablo import API, SpiderSanPablo, hijas

FIXTURES = Path(__file__).parent / "fixtures" / "san_pablo"


@pytest.fixture
def spider():
    crawler = get_crawler(SpiderSanPablo, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderSanPablo.from_crawler(crawler)
    return crawler.spider


def pagina(codigo: str) -> dict:
    return json.loads((FIXTURES / f"categoria_{codigo}.json").read_text(encoding="utf-8"))


def respuesta(datos, codigo: str, numero: int = 0) -> TextResponse:
    url = (f"{API}?query=:relevance:category:{codigo}&pageSize=100"
           f"&currentPage={numero}&fields=FULL&lang=es_MX&curr=MXN")
    cuerpo = datos if isinstance(datos, bytes) else json.dumps(datos).encode()
    return TextResponse(url, body=cuerpo, encoding="utf-8",
                        request=Request(url))


def separar(salida) -> tuple[list[dict], list[Request]]:
    salida = list(salida)
    return ([x for x in salida if isinstance(x, dict)],
            [x for x in salida if isinstance(x, Request)])


def test_hijas_baja_un_nivel_e_ignora_campanas():
    assert hijas("06", pagina("06")["facets"]) == [
        "06001", "06002", "06003", "06004", "06005", "06006", "06007",
        "06008", "06010", "06011"]
    assert hijas("06011", pagina("06011")["facets"]) == [
        f"06011000{n}" for n in range(1, 10)]
    assert hijas("060110001", pagina("060110001")["facets"]) == []


def test_departamento_sobre_el_tope_baja_a_sus_categorias(spider):
    filas, peticiones = separar(spider.parse(
        respuesta(pagina("06"), "06"), categoria="06", codigo="06",
        numero=0))
    # Sus productos vuelven a salir en las hijas: aquí no se emiten.
    assert not filas
    assert [p.cb_kwargs["codigo"] for p in peticiones][-1] == "06011"
    assert len(peticiones) == 10
    assert all(p.cb_kwargs["categoria"] == "06" for p in peticiones)
    assert peticiones[0].headers["Accept"] == b"application/json"
    assert spider.total_reportado == 5419
    assert spider.por_categoria["06"]["total_reportado"] == 5419
    assert "06" not in spider.sin_datos


def test_categoria_sobre_el_tope_baja_a_subcategorias(spider):
    spider.por_categoria["06"] = {"total_reportado": 5419, "skus": set()}
    _, peticiones = separar(spider.parse(
        respuesta(pagina("06011"), "06011"), categoria="06", codigo="06011",
        numero=0))
    assert len(peticiones) == 9
    # La partición no suma al total: ya lo puso el departamento.
    assert spider.por_categoria["06"]["total_reportado"] == 5419


def test_subcategoria_bajo_el_tope_pagina_y_emite_filas(spider):
    spider.por_categoria["06"] = {"total_reportado": 5419, "skus": set()}
    filas, peticiones = separar(spider.parse(
        respuesta(pagina("060110001"), "060110001"), categoria="06",
        codigo="060110001", numero=0))
    # 676 productos en páginas de 100: 6 más la primera.
    assert [p.cb_kwargs["numero"] for p in peticiones] == [1, 2, 3, 4, 5, 6]
    assert "currentPage=6&" in peticiones[-1].url
    assert len(filas) == 5
    assert spider.por_categoria["06"]["skus"] == {
        f["sku_tienda"] for f in filas}
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "sanpablo",
                    "escalon": "b"}
        assert validar(completa, "sanpablo") is None, fila["sku_tienda"]
    fila = filas[0]
    assert len(fila["sku_tienda"]) == 18
    assert fila["url_producto"].startswith(
        "https://www.farmaciasanpablo.com.mx/medicamentos/")
    assert fila["categoria_ruta"] == ["medicamentos", "supervision-medica",
                                      "a---b---c"]
    assert fila["zona_precio"] == "sin_ubicacion"
    assert "Fsp275Wx275H" in fila["url_imagen"]
    # basePrice es la venta y price la lista, como en el legado.
    descuento = [f for f in filas if f["precio_oferta"]]
    assert descuento and all(f["precio_lista"] > f["precio_oferta"]
                             for f in descuento)


def test_sin_descuento_un_solo_precio(spider):
    producto = {**pagina("060110001")["products"][0],
                "price": {"value": 367.0}, "basePrice": {"value": 367.0}}
    fila = spider.fila(producto, None, "")
    assert (fila["precio_lista"], fila["precio_oferta"]) == (
        Decimal("367.0"), None)


def test_respuesta_xml_se_pide_otra_vez(spider):
    xml = b"<productCategorySearchPage/>"
    [otra] = spider.parse(respuesta(xml, "06"), categoria="06", codigo="06",
                          numero=0)
    assert otra.dont_filter
    assert spider.crawler.stats.get_value(
        "sanpablo/paginas_sin_datos") == 1


def test_corre_sin_cookies():
    crawler = get_crawler(SpiderSanPablo, {"AXIOM_ENTORNO": "oficina"})
    assert crawler.settings.getbool("COOKIES_ENABLED") is False
