"""Pruebas de la ingesta de precios_v2 (Scrapers 2.0) hasta bronce P1.

Las unitarias no tocan la red. La de integración usa BigQuery y GCS reales
con `tienda="__test__"`, manifest y tabla de corridas desechables, y se salta
sin credenciales ADC.
"""

import hashlib
import io
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from precios_load import bq, precios_v2

# Copia mínima del contrato v1 de scrapers/ (precios_scrapers/contrato.py):
# load/ no depende de ese paquete, así que la prueba escribe lo mismo que él.
CONTRATO = pa.schema([
    ("contrato_version", pa.string()), ("corrida_id", pa.string()),
    ("tienda", pa.string()), ("capturado_en", pa.timestamp("us", tz="UTC")),
    ("url_producto", pa.string()), ("sku_tienda", pa.string()),
    ("producto", pa.string()), ("marca", pa.string()), ("ean", pa.string()),
    ("categoria_ruta", pa.list_(pa.string())),
    ("precio_lista", pa.decimal128(12, 2)),
    ("precio_oferta", pa.decimal128(12, 2)), ("moneda", pa.string()),
    ("disponible", pa.bool_()), ("url_imagen", pa.string()),
    ("zona_precio", pa.string()), ("escalon", pa.string()),
    ("url_fuente", pa.string()),
    ("atributos_tienda", pa.map_(pa.string(), pa.string())),
])


def fila_contrato(i: int, corrida_id: str, tienda: str = "__test__") -> dict:
    return {
        "contrato_version": "1.0.0", "corrida_id": corrida_id,
        "tienda": tienda,
        # 03:00 UTC del 1 de octubre es 21:00 del 30 de septiembre en CDMX.
        "capturado_en": datetime(2026, 10, 1, 3, 0, tzinfo=UTC),
        "url_producto": f"https://tienda.mx/p/{i}", "sku_tienda": str(i),
        "producto": f"Producto {i}", "marca": "Marca", "ean": "7501098610010",
        "categoria_ruta": ["Farmacia", "Medicina"],
        "precio_lista": Decimal("120.50"), "precio_oferta": Decimal("99.00"),
        "moneda": "MXN", "disponible": True, "url_imagen": None,
        "zona_precio": None, "escalon": "b",
        "url_fuente": "https://tienda.mx/farmacia",
        "atributos_tienda": [("vendedor", "Tienda")],
    }


def escribir_corrida(raiz, tienda: str, corrida_id: str, estado: str,
                     filas: int = 3, anio_mes: str = "2026-10",
                     md5_falso: bool = False) -> str:
    """Deja una corrida como la escribe el pipeline Parquet de scrapers/."""
    carpeta = raiz / f"tienda={tienda}/anio_mes={anio_mes}/corrida={corrida_id}"
    carpeta.mkdir(parents=True)
    tabla = pa.Table.from_pylist(
        [fila_contrato(i, corrida_id, tienda) for i in range(filas)],
        schema=CONTRATO)
    buffer = io.BytesIO()
    pq.write_table(tabla, buffer)
    (carpeta / "parte-0001.parquet").write_bytes(buffer.getvalue())
    md5 = "0" * 32 if md5_falso else hashlib.md5(buffer.getvalue()).hexdigest()
    corrida = {"corrida_id": corrida_id, "tienda": tienda,
               "contrato_version": "1.0.0", "estado": estado,
               "razon_cierre": "finished" if estado == "completa" else "shutdown",
               "inicio": "2026-10-01T03:00:00+00:00",
               "fin": "2026-10-01T03:10:00+00:00",
               "partes": [{"nombre": "parte-0001.parquet", "filas": filas,
                           "md5": md5}],
               "filas_total": filas, "unicos": filas, "total_reportado": filas,
               "cobertura": 1.0, "peticiones": 2,
               "respuestas_por_status": {"200": 2}, "bloqueos": 0,
               "reintentos": 0, "escalon": "b", "entorno": "oficina",
               "version_codigo": "abc"}
    (carpeta / "_corrida.json").write_text(json.dumps(corrida),
                                           encoding="utf-8")
    return corrida_id


def test_a_p1_mapea_contrato_y_hora_local(tmp_path):
    escribir_corrida(tmp_path, "__test__", "__test___20261001T0300Z",
                     "completa")
    sistema, raiz, corridas = precios_v2.descubrir(str(tmp_path))
    (parte,) = precios_v2.leer_partes(sistema, raiz, corridas[0])
    assert parte.ruta == ("precios_v2/tienda=__test__/anio_mes=2026-10/"
                          "corrida=__test___20261001T0300Z/parte-0001.parquet")

    tabla = precios_v2.a_p1(parte, datetime.now(UTC))
    assert tabla.schema.equals(precios_v2.ESQUEMA_P1)
    fila = tabla.to_pylist()[0]
    assert fila["fecha_captura"] == datetime(2026, 9, 30, 21, 0, tzinfo=UTC)
    assert fila["capturado_en_utc"] == datetime(2026, 10, 1, 3, 0, tzinfo=UTC)
    assert (fila["anio_mes_dato"], fila["desfase_mes"]) == ("2026-09", True)
    assert fila["precio_actual"] == Decimal("120.50")
    assert fila["precio_oferta_raw"] == "99.00"
    assert fila["sku"] == fila["sku_raw"] == "0"
    assert fila["_variante_schema"] == "P1"
    assert fila["categoria_ruta"] == ["Farmacia", "Medicina"]
    assert fila["atributos_tienda"] == [("vendedor", "Tienda")]


def test_md5_que_no_cuadra_falla(tmp_path):
    escribir_corrida(tmp_path, "__test__", "c1", "completa", md5_falso=True)
    sistema, raiz, corridas = precios_v2.descubrir(str(tmp_path))
    with pytest.raises(precios_v2.ErrorPartes, match="MD5"):
        precios_v2.leer_partes(sistema, raiz, corridas[0])


def test_origen_vacio_no_falla(tmp_path):
    assert precios_v2.descubrir(str(tmp_path / "no_existe"))[2] == []


@pytest.fixture
def tabla_corridas_tmp(cliente_bq, cfg_gcp):
    """Tabla de corridas desechable; nunca se toca `_corridas_scraping`."""
    nombre = f"_corridas_scraping_test_{uuid4().hex[:8]}"
    yield nombre
    cliente_bq.delete_table(cfg_gcp.tabla_ops(nombre), not_found_ok=True)


def test_ingesta_v2_hasta_bronce_y_precios_ext(
    tmp_path, cliente_bq, cliente_gcs, cfg_gcp, limpiar_bronce,
    tabla_manifest_tmp, tabla_corridas_tmp, tabla_ext_tmp,
):
    sufijo = uuid4().hex[:8]
    completa = escribir_corrida(tmp_path, "__test__", f"__test___{sufijo}",
                                "completa", filas=3)
    escribir_corrida(tmp_path, "__test__", f"__test___{sufijo}p", "parcial")
    # Se registra antes de correr para que el teardown limpie aunque falle.
    limpiar_bronce(cfg_gcp.uri_bronce(
        "__test__", "2026-10", f"{completa}_parte-0001.parquet"))
    limpiar_bronce(cfg_gcp.uri_bronce(
        "__test__", "2026-10", f"__test___{sufijo}p_parte-0001.parquet"))

    def ingerir():
        return precios_v2.ejecutar(
            cliente_bq, cliente_gcs, cfg_gcp, str(tmp_path),
            tabla_manifest=tabla_manifest_tmp,
            tabla_corridas=tabla_corridas_tmp)

    primera = ingerir()
    assert len(primera.procesadas) == 1 and not primera.fallidas
    assert primera.corridas_omitidas == (
        f"tienda=__test__/anio_mes=2026-10/corrida=__test___{sufijo}p",)
    assert primera.jsons_cargados == 2

    segunda = ingerir()
    assert segunda.procesadas == () and len(segunda.saltadas) == 1
    assert segunda.jsons_cargados == 0

    corridas = {f["corrida_id"]: f["estado"] for f in cliente_bq.query(
        f"SELECT corrida_id, estado FROM "
        f"`{cfg_gcp.tabla_ops(tabla_corridas_tmp)}`").result()}
    assert corridas == {completa: "completa",
                        f"__test___{sufijo}p": "parcial"}

    # precios_ext con el DDL nuevo lee el histórico real y P1 juntos.
    ref = bq.crear_external_bronce(cliente_bq, cfg_gcp, tabla_ext_tmp)
    (resumen,) = cliente_bq.query(f"""
        SELECT
          COUNTIF(_variante_schema = 'P1' AND tienda = '__test__'
                  AND corrida_id = '{completa}') AS p1,
          COUNTIF(_variante_schema != 'P1') AS historico,
          COUNTIF(_variante_schema != 'P1' AND corrida_id IS NOT NULL)
            AS historico_con_columnas_nuevas,
          MAX(IF(corrida_id = '{completa}',
                 ARRAY_LENGTH(categoria_ruta.list), NULL)) AS categorias
        FROM `{ref}`
    """).result()
    assert resumen["p1"] == 3
    assert resumen["historico"] > 0
    assert resumen["historico_con_columnas_nuevas"] == 0
    assert resumen["categorias"] == 2
