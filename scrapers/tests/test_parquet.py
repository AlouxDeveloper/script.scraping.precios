"""Pruebas del pipeline Parquet: partes, _corrida.json y corridas cortadas."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import pyarrow.parquet as pq
import pytest
from scrapy.utils.test import get_crawler

from precios_scrapers.pipelines.parquet import PipelineParquet, estado_por_razon
from precios_scrapers.spiders.prueba import SpiderPrueba


def armar(tmp_path, filas_por_parte=1000):
    crawler = get_crawler(SpiderPrueba, {
        "AXIOM_ENTORNO": "oficina", "AXIOM_DESTINO": str(tmp_path),
        "PARQUET_FILAS_POR_PARTE": filas_por_parte})
    crawler.spider = SpiderPrueba.from_crawler(crawler)
    # 2026-10-01 03:00 UTC es todavía septiembre en la Ciudad de México.
    crawler.spider.inicio = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)
    pipeline = PipelineParquet.from_crawler(crawler)
    pipeline.open_spider()
    return pipeline


def fila(i: int) -> dict:
    return {"contrato_version": "1.0.0", "corrida_id": "prueba_20261001T0300Z",
            "tienda": "prueba", "escalon": "b", "moneda": "MXN",
            "capturado_en": datetime.now(timezone.utc),
            "url_producto": f"https://prueba.invalid/p/{i}",
            "sku_tienda": str(i), "producto": f"Producto {i}",
            "precio_lista": Decimal("10.00"), "url_fuente": "https://x.invalid"}


def corrida(pipeline) -> dict:
    with open(f"{pipeline.carpeta}/_corrida.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("razon, estado", [
    ("finished", "completa"), ("shutdown", "parcial"),
    ("closespider_itemcount", "parcial"), ("bloqueo_sostenido", "abortada")])
def test_estado_por_razon(razon, estado):
    assert estado_por_razon(razon) == estado


def test_corrida_completa(tmp_path):
    pipeline = armar(tmp_path)
    assert "/anio_mes=2026-09/" in pipeline.carpeta
    for i in range(2500):
        pipeline.process_item(fila(i))
    pipeline.cerrar(pipeline.crawler.spider, reason="finished")

    datos = corrida(pipeline)
    assert datos["estado"] == "completa"
    assert [p["filas"] for p in datos["partes"]] == [1000, 1000, 500]
    assert datos["filas_total"] == datos["unicos"] == 2500
    for parte in datos["partes"]:
        ruta = f"{pipeline.carpeta}/{parte['nombre']}"
        with open(ruta, "rb") as f:
            assert hashlib.md5(f.read()).hexdigest() == parte["md5"]
    assert pq.read_schema(ruta).metadata[b"contrato_version"] == b"1.0.0"


def test_proceso_muerto_deja_partes_y_estado_parcial(tmp_path):
    pipeline = armar(tmp_path)
    for i in range(2500):
        pipeline.process_item(fila(i))
    # Sin cerrar(): así queda el disco si el proceso muere aquí. Se pierde
    # solo el lote en memoria (500 filas).
    datos = corrida(pipeline)
    assert datos["estado"] == "parcial"
    assert datos["filas_total"] == 2000
    assert sorted(p.name for p in tmp_path.rglob("*.parquet")) == [
        "parte-0001.parquet", "parte-0002.parquet"]
