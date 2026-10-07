"""Pruebas del contrato v1: esquema versionado, reglas y pipeline."""
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from scrapy.exceptions import DropItem
from scrapy.utils.test import get_crawler

from precios_scrapers.contrato import CONTRATO_VERSION, ESQUEMA
from precios_scrapers.pipelines.contrato import PipelineContrato, validar
from precios_scrapers.spiders.base import RUTA_TIENDAS
from precios_scrapers.spiders.prueba import SpiderPrueba

# Huella de cada versión publicada del esquema. Si cambias ESQUEMA, sube
# CONTRATO_VERSION (PRD, sección 4.5) y agrega aquí la huella nueva.
HUELLAS = {
    "1.0.0": "644530c6526ae6acfab4bb2b6e0bcdc46123447f519c41907132037ff4ace418",
}
ARCHIVOS_YML = Path(__file__).resolve().parents[2] / "load/config/archivos.yml"


def item_bueno(**cambios) -> dict:
    item = {
        "contrato_version": CONTRATO_VERSION,
        "corrida_id": "prueba_20261007T1742Z",
        "tienda": "prueba",
        "capturado_en": datetime(2026, 10, 7, 17, 42, tzinfo=timezone.utc),
        "url_producto": "https://tienda.mx/p/1",
        "sku_tienda": "1184105",
        "producto": "Naxen 550 mg 12 tabletas",
        "marca": "Naxen",
        "ean": "7501098610010",
        "categoria_ruta": ["Farmacia", "Medicina"],
        "precio_lista": Decimal("120.50"),
        "precio_oferta": Decimal("99.00"),
        "moneda": "MXN",
        "disponible": True,
        "url_imagen": "https://tienda.mx/img/1.jpg",
        "zona_precio": None,
        "escalon": "b",
        "url_fuente": "https://tienda.mx/farmacia?start=0&sz=96",
        "atributos_tienda": {"vendedor": "Walmart"},
    }
    item.update(cambios)
    return item


def test_esquema_no_cambia_sin_subir_version():
    huella = hashlib.sha256(
        ESQUEMA.to_string(show_schema_metadata=False).encode()).hexdigest()
    assert HUELLAS.get(CONTRATO_VERSION) == huella, (
        "ESQUEMA cambió: sube CONTRATO_VERSION y registra su huella")
    assert ESQUEMA.metadata[b"contrato_version"] == CONTRATO_VERSION.encode()


def test_slugs_de_tiendas_existen_en_load():
    tiendas = set(yaml.safe_load(RUTA_TIENDAS.read_text(encoding="utf-8")))
    archivos = yaml.safe_load(ARCHIVOS_YML.read_text(encoding="utf-8"))
    legado = {a["tienda"] for a in archivos["archivos"]}
    assert tiendas - {"prueba"} <= legado


@pytest.mark.parametrize("cambios", [
    {},
    {"precio_oferta": None},
    {"precio_lista": None},
    {"marca": None, "ean": None, "categoria_ruta": None, "disponible": None,
     "url_imagen": None, "atributos_tienda": None},
    {"precio_lista": 145},
    {"zona_precio": "2344"},
])
def test_item_bueno(cambios):
    assert validar(item_bueno(**cambios), "prueba") is None


@pytest.mark.parametrize("cambios, regla", [
    ({"extra": "x"}, "campo_desconocido"),
    ({"sku_tienda": None}, "nulo/sku_tienda"),
    ({"producto": None}, "nulo/producto"),
    ({"precio_lista": 120.5}, "tipo/precio_lista"),
    ({"precio_lista": Decimal("120.505")}, "tipo/precio_lista"),
    ({"sku_tienda": 1184105}, "tipo/sku_tienda"),
    ({"disponible": "si"}, "tipo/disponible"),
    ({"categoria_ruta": "Farmacia"}, "tipo/categoria_ruta"),
    ({"capturado_en": datetime(2026, 10, 7, 17, 42)}, "capturado_en_no_utc"),
    ({"capturado_en": datetime(2026, 10, 7, 11, 42,
                               tzinfo=timezone(timedelta(hours=-6)))},
     "capturado_en_no_utc"),
    ({"precio_lista": None, "precio_oferta": None}, "precio_ausente"),
    ({"precio_lista": Decimal("0")}, "precio_lista_no_positivo"),
    ({"precio_lista": None, "precio_oferta": Decimal("-1")},
     "precio_oferta_no_positivo"),
    ({"precio_oferta": Decimal("120.50")}, "precio_oferta_no_menor"),
    ({"precio_oferta": Decimal("130")}, "precio_oferta_no_menor"),
    ({"moneda": "USD"}, "moneda"),
    ({"tienda": "walmart"}, "tienda"),
    ({"sku_tienda": "N/A"}, "sku_centinela"),
    ({"sku_tienda": "search"}, "sku_centinela"),
    ({"sku_tienda": " "}, "sku_centinela"),
    ({"url_imagen": "data:image/png;base64,iVBORw0KGgo="}, "imagen_no_url"),
    ({"ean": "750-109"}, "ean_no_digitos"),
    ({"escalon": "e"}, "escalon"),
    ({"contrato_version": "0.9.0"}, "contrato_version"),
    ({"corrida_id": "prueba"}, "corrida_id"),
])
def test_item_malo(cambios, regla):
    assert validar(item_bueno(**cambios), "prueba") == regla


def test_pipeline_completa_rechaza_y_deduplica():
    crawler = get_crawler(SpiderPrueba, {"AXIOM_ENTORNO": "oficina"})
    crawler.spider = SpiderPrueba.from_crawler(crawler)
    pipeline = PipelineContrato.from_crawler(crawler)
    base = item_bueno()
    for campo in ("contrato_version", "corrida_id", "tienda", "escalon"):
        del base[campo]

    aceptado = pipeline.process_item(dict(base))
    assert aceptado["tienda"] == "prueba"
    assert aceptado["corrida_id"] == crawler.spider.corrida_id
    with pytest.raises(DropItem, match="duplicado"):
        pipeline.process_item(dict(base))
    # Otra zona del mismo SKU no es duplicado.
    pipeline.process_item(dict(base, zona_precio="2344"))
    with pytest.raises(DropItem, match="moneda"):
        pipeline.process_item(dict(base, moneda="USD", sku_tienda="2"))

    stats = crawler.stats.get_stats()
    assert stats["contrato/aceptados"] == 2
    assert stats["contrato/duplicados"] == 1
    assert stats["contrato/rechazados"] == 1
    assert stats["contrato/rechazados/moneda"] == 1
