"""Pruebas de SpiderTienda: entorno permitido, tráfico y meta por escalón."""
import pytest
from scrapy.utils.test import get_crawler

from precios_scrapers.spiders.base import EntornoNoPermitido
from precios_scrapers.spiders.prueba import SpiderPrueba


def test_aborta_en_entorno_no_permitido():
    crawler = get_crawler(SpiderPrueba, {"AXIOM_ENTORNO": "gcp"})
    with pytest.raises(EntornoNoPermitido, match="'gcp'"):
        SpiderPrueba.from_crawler(crawler)


def test_entorno_permitido_aplica_trafico_e_impersonacion():
    crawler = get_crawler(SpiderPrueba, {"AXIOM_ENTORNO": "oficina"})
    spider = SpiderPrueba.from_crawler(crawler)
    assert spider.impersonate == "chrome"
    assert spider.corrida_id.startswith("prueba_")
    assert crawler.settings.getfloat("DOWNLOAD_DELAY") == 1.5
