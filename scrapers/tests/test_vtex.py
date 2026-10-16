"""Pruebas offline de la base VTEX y de los spiders de sus cuatro tiendas.

Fixtures de ``catalog_system`` sobre Medicamentos de Chedraui
(``fq=C:/4/403/``), Farmatodo (``fq=C:/7/``) y Similares (``fq=C:/29/``), y
Patente de Klyns (``fq=C:/68/``), 2026-10-15, recortados con
``fixtures/chedraui/recortar.py``: los 3 primeros productos y 2 con
descuento. El total va en el header ``resources``, que cada
prueba pone según el caso.
"""
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote

import pytest
from scrapy import Request
from scrapy.http import TextResponse
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION
from precios_scrapers.pipelines.contrato import validar
from precios_scrapers.spiders.vtex import (TOPE, SpiderChedraui,
                                          SpiderFarmatodo, SpiderKlyns,
                                          SpiderSimilares, SpiderVtex)

FIXTURES = Path(__file__).parent / "fixtures" / "chedraui"
API = "https://www.chedraui.com.mx/api/catalog_system/pub/products/search"
MEDICAMENTOS = "/4/403/"


@pytest.fixture
def spider():
    crawler = get_crawler(SpiderChedraui, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderChedraui.from_crawler(crawler)
    return crawler.spider


def productos() -> list[dict]:
    return json.loads((FIXTURES / "medicamentos_p1.json").read_text(encoding="utf-8"))


def respuesta(url: str, total: int | None, cuerpo=None) -> TextResponse:
    headers = {"resources": f"0-49/{total}"} if total is not None else {}
    cuerpo = productos() if cuerpo is None else cuerpo
    return TextResponse(url, body=json.dumps(cuerpo).encode(),
                        encoding="utf-8", headers=headers,
                        request=Request(url))


def separar(salida) -> tuple[list[dict], list[Request]]:
    salida = list(salida)
    return ([x for x in salida if isinstance(x, dict)],
            [x for x in salida if isinstance(x, Request)])


def test_categoria_sobre_el_tope_se_parte_por_precio(spider):
    url = f"{API}?fq=C:{MEDICAMENTOS}&_from=0&_to=49"
    filas, peticiones = separar(spider.parse(
        respuesta(url, 3383), categoria=MEDICAMENTOS, rango=None, inicio=0))
    # Sus productos vuelven a salir en los rangos: aquí no se emiten.
    assert not filas
    assert len(peticiones) == 2
    abajo, arriba = (p.cb_kwargs["rango"] for p in peticiones)
    assert abajo[0] == 0 and arriba[0] == abajo[1] + 1
    assert all("P:[" in unquote(p.url) and "_from=0&" in p.url
               for p in peticiones)
    assert spider.total_reportado == 3383
    assert spider.por_categoria[MEDICAMENTOS]["total_reportado"] == 3383
    assert MEDICAMENTOS not in spider.sin_datos


def test_rango_que_cabe_pagina_y_emite_filas(spider):
    spider.por_categoria[MEDICAMENTOS] = {"total_reportado": 3383,
                                          "skus": set()}
    url = f"{API}?fq=C:{MEDICAMENTOS}&fq=P:%5B0.00%20TO%2025.00%5D"
    filas, peticiones = separar(spider.parse(
        respuesta(url, 120), categoria=MEDICAMENTOS, rango=(0, 2500),
        inicio=0))
    assert [p.cb_kwargs["inicio"] for p in peticiones] == [50, 100]
    assert "fq=P:%5B0.00%20TO%2025.00%5D&_from=100&_to=149" in peticiones[-1].url
    assert len(filas) == 5
    assert spider.por_categoria[MEDICAMENTOS]["skus"] == {
        f["sku_tienda"] for f in filas}


def test_filas_cumplen_el_contrato(spider):
    spider.por_categoria[MEDICAMENTOS] = {"total_reportado": 5, "skus": set()}
    url = f"{API}?fq=C:{MEDICAMENTOS}&_from=0&_to=49"
    filas, _ = separar(spider.parse(respuesta(url, 5), categoria=MEDICAMENTOS,
                                    rango=None, inicio=0))
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "chedraui",
                    "escalon": "a"}
        assert validar(completa, "chedraui") is None, fila["sku_tienda"]
    fila = filas[0]
    assert fila["sku_tienda"] == "3347259"
    assert fila["url_producto"].startswith("https://www.chedraui.com.mx/")
    assert fila["categoria_ruta"] == ["Farmacia", "Medicamentos",
                                      "Estomacales"]
    assert fila["zona_precio"] == "sin_region"
    assert fila["ean"].isdigit()
    assert "?" not in fila["url_imagen"]
    # Sin descuento: un solo precio, en precio_lista.
    assert fila["precio_lista"] == Decimal("26") and fila["precio_oferta"] is None
    descuento = next(f for f in filas if f["sku_tienda"] == "3821128")
    assert (descuento["precio_lista"], descuento["precio_oferta"]) == (
        Decimal("26"), Decimal("25"))


def test_sin_precio_ni_items_no_emite_pero_cuenta(spider):
    spider.por_categoria[MEDICAMENTOS] = {"total_reportado": 2, "skus": set()}
    sin_precio, sin_items = productos()[:2]
    sin_precio["items"][0]["sellers"][0]["commertialOffer"]["Price"] = 0
    sin_items["items"] = []
    url = f"{API}?fq=C:{MEDICAMENTOS}&_from=0&_to=49"
    filas, _ = separar(spider.parse(
        respuesta(url, 2, [sin_precio, sin_items]), categoria=MEDICAMENTOS,
        rango=None, inicio=0))
    assert not filas
    stats = spider.crawler.stats
    assert stats.get_value("chedraui/sin_precio") == 1
    assert stats.get_value("chedraui/sin_items") == 1
    # El visto sin precio sí cuenta para la cobertura: estaba en el listado.
    assert spider.por_categoria[MEDICAMENTOS]["skus"] == {"3347259"}


def test_pagina_sin_resources_se_pide_otra_vez(spider):
    url = f"{API}?fq=C:{MEDICAMENTOS}&_from=0&_to=49"
    [otra] = spider.parse(respuesta(url, None), categoria=MEDICAMENTOS,
                          rango=None, inicio=0)
    assert otra.url == url and otra.dont_filter
    assert spider.crawler.stats.get_value("chedraui/paginas_sin_datos") == 1


def test_partir_corta_sin_traslape_ni_hueco():
    abajo, arriba = SpiderVtex.partir((0, 10_000_000), productos())
    # La mediana de los precios de la página ($25) y no la mitad del rango.
    assert abajo == (0, 2500) and arriba == (2501, 10_000_000)
    assert SpiderVtex.partir((2600, 2600), productos()) is None
    # Una mediana fuera del rango cae a la mitad.
    assert SpiderVtex.partir((5000, 7000), productos()) == [(5000, 6000),
                                                           (6001, 7000)]


def test_campo_sku_configurable(spider):
    spider.campo_sku = "ean"
    producto = productos()[0]
    assert spider.sku(producto) == producto["items"][0]["ean"]


def test_ultima_pagina_alcanzable_respeta_el_tope(spider):
    spider.por_categoria[MEDICAMENTOS] = {"total_reportado": 9000,
                                          "skus": set()}
    url = f"{API}?fq=C:{MEDICAMENTOS}&fq=P:%5B26.00%20TO%2026.00%5D"
    _, peticiones = separar(spider.parse(
        respuesta(url, 9000), categoria=MEDICAMENTOS, rango=(2600, 2600),
        inicio=0))
    assert max(p.cb_kwargs["inicio"] for p in peticiones) == TOPE - 50
    assert spider.crawler.stats.get_value("chedraui/rangos_recortados") == 1


def test_farmatodo_usa_productreference_y_su_dominio():
    crawler = get_crawler(SpiderFarmatodo, {"AXIOM_ENTORNO": "oficina"})
    spider = crawler.spider = SpiderFarmatodo.from_crawler(crawler)
    spider.por_categoria["/7/"] = {"total_reportado": 5, "skus": set()}
    cuerpo = json.loads(
        (Path(__file__).parent / "fixtures" / "farmatodo"
         / "medicamentos_p1.json").read_text(encoding="utf-8"))
    url = ("https://www.farmatodo.com.mx/api/catalog_system/pub/products/"
           "search?fq=C:/7/&_from=0&_to=49")
    filas, _ = separar(spider.parse(respuesta(url, 5, cuerpo),
                                    categoria="/7/", rango=None, inicio=0))
    assert len(filas) == 5
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "farmatodo",
                    "escalon": "a"}
        assert validar(completa, "farmatodo") is None, fila["sku_tienda"]
    # El SKU del legado es el EAN (productReference), no el productId.
    assert filas[0]["sku_tienda"] == "7501159580021" == filas[0]["ean"]
    assert filas[0]["url_producto"].startswith("https://www.farmatodo.com.mx/")
    assert any(f["precio_oferta"] for f in filas)
    assert spider.pedir("/7/", None, 0).url.startswith(
        "https://www.farmatodo.com.mx/api/catalog_system/pub/products/search"
        "?fq=C:/7/")


def test_klyns_usa_el_ean_y_guarda_el_refid():
    crawler = get_crawler(SpiderKlyns, {"AXIOM_ENTORNO": "oficina"})
    spider = crawler.spider = SpiderKlyns.from_crawler(crawler)
    spider.por_categoria["/68/"] = {"total_reportado": 5, "skus": set()}
    cuerpo = json.loads((Path(__file__).parent / "fixtures" / "klyns"
                         / "patente_p1.json").read_text(encoding="utf-8"))
    url = ("https://www.klyns.mx/api/catalog_system/pub/products/search"
           "?fq=C:/68/&_from=0&_to=49")
    filas, _ = separar(spider.parse(respuesta(url, 5, cuerpo),
                                    categoria="/68/", rango=None, inicio=0))
    assert len(filas) == 5
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "klyns",
                    "escalon": "a"}
        assert validar(completa, "klyns") is None, fila["sku_tienda"]
    fila = filas[0]
    # SKU = items[0].ean; el RefId del legado queda en atributos_tienda.
    assert fila["sku_tienda"] == "7501125100116" == fila["ean"]
    assert fila["atributos_tienda"] == {"product_reference": "100009121"}
    # Descuento permanente de Klyns: lista y oferta en todas.
    assert (fila["precio_lista"], fila["precio_oferta"]) == (
        Decimal("38.43"), Decimal("28.44"))
    assert all(f["precio_oferta"] for f in filas)


def test_sin_refid_distinto_no_hay_atributos(spider):
    # En Chedraui productReference = productId = SKU: no se repite.
    fila = spider.fila(productos()[0], None, "")
    assert fila["atributos_tienda"] == {}


def test_similares_sin_ean_y_sku_interno():
    crawler = get_crawler(SpiderSimilares, {"AXIOM_ENTORNO": "oficina"})
    spider = crawler.spider = SpiderSimilares.from_crawler(crawler)
    spider.por_categoria["/29/"] = {"total_reportado": 3, "skus": set()}
    cuerpo = json.loads((Path(__file__).parent / "fixtures" / "similares"
                         / "medicamentos_p1.json").read_text(encoding="utf-8"))
    url = ("https://www.farmaciasdesimilares.com/api/catalog_system/pub/"
           "products/search?fq=C:/29/&_from=0&_to=49")
    filas, peticiones = separar(spider.parse(
        respuesta(url, 3, cuerpo), categoria="/29/", rango=None, inicio=0))
    assert not peticiones and len(filas) == 3
    for fila in filas:
        completa = {**fila, "contrato_version": CONTRATO_VERSION,
                    "corrida_id": spider.corrida_id, "tienda": "similares",
                    "escalon": "a"}
        assert validar(completa, "similares") is None, fila["sku_tienda"]
    # El ean de Similares es su código interno: no se guarda como EAN.
    assert all(f["ean"] is None for f in filas)
    assert filas[0]["sku_tienda"] == "2315"
    assert filas[0]["atributos_tienda"] == {}
