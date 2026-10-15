"""Pruebas offline del spider de GI con respuestas reales recortadas.

Fixture de la Store API (2026-10-15) recortado con
``fixtures/gi/recortar.py``: los 3 primeros productos del catálogo más uno
sin SKU (Portem), uno con precio 0 (Flanax) y uno con entidades HTML en el
nombre (Playboy). El total va en los headers de WooCommerce, que cada prueba
pone según el caso.
"""
from decimal import Decimal
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import TextResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.gi import API, SpiderGi

FIXTURE = Path(__file__).parent / "fixtures" / "gi" / "catalogo_p1.json"
URL = f"{API}?per_page=100&page=1"


@pytest.fixture
def spider():
    crawler = get_crawler(SpiderGi, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderGi.from_crawler(crawler)
    return crawler.spider


def respuesta(url: str = URL, cuerpo: bytes | None = None,
              total: int | None = 1778) -> TextResponse:
    headers = ({"x-wp-total": str(total),
                "x-wp-totalpages": str(-(-total // 100))}
               if total is not None else {})
    return TextResponse(url, body=cuerpo or FIXTURE.read_bytes(),
                        encoding="utf-8", headers=headers,
                        request=Request(url))


def separar(salida) -> tuple[list[dict], list[Request]]:
    salida = list(salida)
    return ([x for x in salida if isinstance(x, dict)],
            [x for x in salida if isinstance(x, Request)])


def test_todo_recorre_el_catalogo_sin_filtro(spider):
    peticion = spider.pagina("todo", 1)
    assert peticion.url == URL
    assert "category" not in peticion.url
    assert spider.pagina("53", 2).url.endswith("&page=2&category=53")


def test_primera_pagina_pide_las_demas(spider):
    filas, peticiones = separar(spider.parse(respuesta(), categoria="todo",
                                             numero=1))
    # 1,778 productos en páginas de 100: 17 más la primera.
    assert [p.cb_kwargs["numero"] for p in peticiones] == list(range(2, 19))
    assert spider.total_reportado == 1778
    assert "todo" not in spider.sin_datos
    # Flanax (precio 0) se ve pero no se emite.
    assert len(filas) == 5
    assert len(spider.por_categoria["todo"]["skus"]) == 6
    assert spider.crawler.stats.get_value("gi/sin_precio") == 1


def test_filas_cumplen_el_contrato(spider):
    filas, _ = separar(spider.parse(respuesta(), categoria="todo", numero=1))
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "gi",
                    "escalon": "a"}
        assert validar(completa, "gi") is None, fila["sku_tienda"]
    por_sku = {f["sku_tienda"]: f for f in filas}
    # Precio en centavos: "11000" son $110.00, sin descuento.
    bic = por_sku["513693"]
    assert (bic["precio_lista"], bic["precio_oferta"]) == (Decimal("110"),
                                                           None)
    assert bic["url_producto"].startswith("https://farmaciasgi.com.mx/")
    assert bic["zona_precio"] == "sin_ubicacion"
    assert bic["categoria_ruta"] == ["OTROS"]
    # Sin SKU: el ID de WooCommerce con prefijo.
    assert por_sku["wc_52950"]["producto"].startswith("PORTEM")
    assert por_sku["wc_52950"]["categoria_ruta"] == []
    assert por_sku["513274"]["producto"] == "PLAYBOY CONDOMS MIX & PLAY"
    assert "510219" not in por_sku


def test_oferta_se_separa_del_precio_regular(spider):
    producto = {"id": 1, "sku": "1", "name": "x", "permalink": "https://a/",
                "prices": {"price": "8000", "regular_price": "10000",
                           "currency_minor_unit": 2}}
    fila = spider.fila(producto, None, "")
    assert (fila["precio_lista"], fila["precio_oferta"]) == (Decimal("100"),
                                                             Decimal("80"))


def test_pagina_sin_headers_se_pide_otra_vez(spider):
    [otra] = spider.parse(respuesta(total=None), categoria="todo", numero=1)
    assert otra.dont_filter
    assert spider.crawler.stats.get_value("gi/paginas_sin_datos") == 1
