"""Pruebas offline del spider de Alsuper con respuestas reales recortadas.

Fixtures de la sucursal 6 (2026-10-15): ``/departments/web`` con solo ID y
descripción, y la primera página de Farmacia (``limit=500``, 2,504
productos) recortada con ``fixtures/alsuper/recortar.py``: los 3 primeros y 2
con oferta.
"""
from decimal import Decimal
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import TextResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.alsuper import API, SpiderAlsuper

FIXTURES = Path(__file__).parent / "fixtures" / "alsuper"
URL = f"{API}/ms-products/branch/6?department=Farmacia-18&page=1&limit=500"


@pytest.fixture
def spider():
    crawler = get_crawler(SpiderAlsuper, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderAlsuper.from_crawler(crawler)
    return crawler.spider


def respuesta(fixture: str, url: str = URL, cuerpo=None) -> TextResponse:
    if cuerpo is None:
        cuerpo = (FIXTURES / f"{fixture}.json").read_bytes()
    return TextResponse(url, body=cuerpo, encoding="utf-8",
                        request=Request(url))


def separar(salida) -> tuple[list[dict], list[Request]]:
    salida = list(salida)
    return ([x for x in salida if isinstance(x, dict)],
            [x for x in salida if isinstance(x, Request)])


def primera(spider) -> tuple[list[dict], list[Request]]:
    return separar(spider.parse(respuesta("farmacia_p1"), ident=18,
                                slug="Farmacia-18", numero=1))


def test_departamentos_arman_el_slug_con_la_descripcion(spider):
    spider.tienda["categorias"] = [18]
    [peticion] = spider.parse_departamentos(respuesta(
        "departamentos", f"{API}/departments/web?branch=6"))
    assert peticion.url == URL
    assert peticion.cb_kwargs["ident"] == 18


def test_categoria_dentro_de_un_departamento(spider):
    spider.tienda["categorias"] = ["4:Sueros"]
    [peticion] = spider.parse_departamentos(respuesta(
        "departamentos", f"{API}/departments/web?branch=6"))
    assert "department=Jugos%20y%20Bebidas-4&category=Sueros&" in peticion.url
    assert peticion.cb_kwargs["ident"] == "4:Sueros"


def test_departamento_que_ya_no_existe_queda_sin_datos(spider):
    spider.tienda["categorias"] = [99]
    spider.sin_datos = {99}
    assert not list(spider.parse_departamentos(respuesta(
        "departamentos", f"{API}/departments/web?branch=6")))
    assert spider.sin_datos == {99}


def test_primera_pagina_pide_las_demas(spider):
    filas, peticiones = primera(spider)
    # 2,504 productos en páginas de 500: la última (6) trae 4.
    assert [p.cb_kwargs["numero"] for p in peticiones] == [2, 3, 4, 5, 6]
    assert peticiones[-1].url.endswith("page=6&limit=500")
    assert "ecommerce" not in peticiones[0].url
    assert spider.total_reportado == 2504
    assert spider.por_categoria[18]["skus"] == {f["sku_tienda"] for f in filas}
    assert 18 not in spider.sin_datos


def test_filas_cumplen_el_contrato(spider):
    filas, _ = primera(spider)
    assert len(filas) == 5
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "alsuper",
                    "escalon": "a"}
        assert validar(completa, "alsuper") is None, fila["sku_tienda"]
    fila = filas[0]
    assert fila["sku_tienda"] == "473209"
    assert fila["ean"] == "7502258102374"
    assert fila["url_producto"].startswith("https://alsuper.com/producto/")
    assert fila["categoria_ruta"] == ["Farmacia", "Curación y Rehabilitación",
                                      "Algodón"]
    assert fila["zona_precio"] == "sucursal_6"
    # promotion = "OFERTA" sin descuento real: un solo precio.
    assert (fila["precio_lista"], fila["precio_oferta"]) == (
        Decimal("39.9"), None)
    oferta = next(f for f in filas if f["sku_tienda"] == "472660")
    assert (oferta["precio_lista"], oferta["precio_oferta"]) == (
        Decimal("24.9"), Decimal("22.9"))


def test_pagina_sin_listado_se_pide_otra_vez(spider):
    [otra] = spider.parse(respuesta(None, cuerpo=b'{"message":"x"}'),
                          ident=18, slug="Farmacia-18", numero=1)
    assert otra.dont_filter
    assert spider.crawler.stats.get_value("alsuper/paginas_sin_datos") == 1


def test_manda_user_agent_de_navegador():
    crawler = get_crawler(SpiderAlsuper, {"AXIOM_ENTORNO": "oficina"})
    assert "Chrome/" in crawler.settings["USER_AGENT"]


def test_comodin_cuenta_pero_no_se_emite(spider):
    cuerpo = (b'{"data": {"total_items": 1, "data": [{"id": 523081, '
              b'"name": "COMODIN ULTRA LAB GI . 3 CAJA", "price": 0.01, '
              b'"regular_price": 0.01, "stock": 0, '
              b'"share_url": "https://alsuper.com/producto/comodin-523081"}]}}')
    filas, _ = separar(spider.parse(respuesta(None, cuerpo=cuerpo), ident=18,
                                    slug="Farmacia-18", numero=1))
    assert not filas
    assert spider.por_categoria[18]["skus"] == {"523081"}
    assert spider.crawler.stats.get_value("alsuper/comodines") == 1
