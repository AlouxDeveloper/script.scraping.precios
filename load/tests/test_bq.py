"""Los objetos de BigQuery: la external table de bronce y la nativa de silver.

Integración real: crea tablas desechables (`precios_ext_test_<uuid>`,
`precios_test_<uuid>`) apuntando a los mismos datos que producción, y las borra
en el teardown. Nunca toca `precios_ext` ni `precios_silver.precios`.
"""

import io

import pyarrow as pa
import pyarrow.parquet as pq

from precios_load import bq
from precios_load.bronce import ESQUEMA_BRONCE

# Todo el histórico cargado a bronce hoy (134 archivos, septiembre fuera).
FILAS_HISTORICO = 987_461

# Las 12 columnas de bronce que se llevan a silver, verbatim y en este orden.
COLUMNAS_SILVER = [
    "tienda", "tienda_raw", "sku", "producto", "url_producto", "url_imagen",
    "precio_actual", "precio_oferta", "fecha_captura", "anio_mes",
    "_archivo_origen", "_ingestado_en",
]


def _crear(cliente_bq, cfg_gcp, tabla):
    return bq.crear_external_bronce(cliente_bq, cfg_gcp, tabla=tabla)


def _contar(cliente_bq, tabla, where=""):
    sql = f"SELECT COUNT(*) AS n FROM `{tabla}` {where}"
    return next(iter(cliente_bq.query(sql).result()))["n"]


def test_la_external_table_ve_todo_el_historico(cliente_bq, cfg_gcp, tabla_ext_tmp):
    tabla = _crear(cliente_bq, cfg_gcp, tabla_ext_tmp)

    assert _contar(cliente_bq, tabla) == FILAS_HISTORICO


def test_tienda_y_anio_mes_son_columnas_string_una_sola_vez(
    cliente_bq, cfg_gcp, tabla_ext_tmp
):
    """`tienda`/`anio_mes` están en el Parquet y en el path; BigQuery las fusiona."""
    tabla = _crear(cliente_bq, cfg_gcp, tabla_ext_tmp)

    campos = [(c.name, c.field_type) for c in cliente_bq.get_table(tabla).schema]
    assert campos.count(("tienda", "STRING")) == 1
    assert campos.count(("anio_mes", "STRING")) == 1
    assert [n for n, _ in campos].count("tienda") == 1
    assert [n for n, _ in campos].count("anio_mes") == 1


def test_un_filtro_por_particion_lee_menos_bytes(cliente_bq, cfg_gcp, tabla_ext_tmp):
    tabla = _crear(cliente_bq, cfg_gcp, tabla_ext_tmp)

    completo = cliente_bq.query(f"SELECT SUM(precio_actual) FROM `{tabla}`")
    completo.result()
    podado = cliente_bq.query(
        f"SELECT SUM(precio_actual) FROM `{tabla}` WHERE tienda = 'chedraui'"
    )
    podado.result()

    assert podado.total_bytes_processed < completo.total_bytes_processed


def test_crear_external_bronce_es_idempotente(cliente_bq, cfg_gcp, tabla_ext_tmp):
    tabla = _crear(cliente_bq, cfg_gcp, tabla_ext_tmp)
    de_nuevo = _crear(cliente_bq, cfg_gcp, tabla_ext_tmp)

    assert tabla == de_nuevo
    assert _contar(cliente_bq, tabla) == FILAS_HISTORICO


def test_un_parquet_nuevo_aparece_sin_job_de_carga(
    cliente_bq, cliente_gcs, cfg_gcp, limpiar_bronce, tabla_ext_tmp
):
    """La prueba clave de ALD-23: copiar un Parquet a una partición y verlo ya."""
    particion = ("__test_ald23__", "2099-12")
    uri = cfg_gcp.uri_bronce(*particion, "sonda.parquet")
    objeto = uri.removeprefix(f"gs://{cfg_gcp.bucket_bronce}/")
    limpiar_bronce(uri)

    fila = {campo.name: None for campo in ESQUEMA_BRONCE}
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([fila], schema=ESQUEMA_BRONCE), buffer)
    cliente_gcs.bucket(cfg_gcp.bucket_bronce).blob(objeto).upload_from_string(
        buffer.getvalue(), content_type="application/vnd.apache.parquet"
    )

    tabla = _crear(cliente_bq, cfg_gcp, tabla_ext_tmp)

    where = "WHERE tienda = '__test_ald23__' AND anio_mes = '2099-12'"
    assert _contar(cliente_bq, tabla, where) == 1


# --- Tabla nativa de silver ------------------------------------------------


def _crear_silver(cliente_bq, cfg_gcp, tabla):
    return bq.crear_tabla_silver(cliente_bq, cfg_gcp, tabla=tabla)


def test_silver_es_copia_de_bronce_particionada_y_clusterizada(
    cliente_bq, cfg_gcp, tabla_silver_tmp
):
    tabla = _crear_silver(cliente_bq, cfg_gcp, tabla_silver_tmp)
    meta = cliente_bq.get_table(tabla)

    assert meta.num_rows == FILAS_HISTORICO  # todas las filas, sin filtro
    assert meta.time_partitioning.type_ == "MONTH"
    assert meta.time_partitioning.field == "fecha_captura"
    assert meta.clustering_fields == ["tienda", "sku"]
    assert [c.name for c in meta.schema] == COLUMNAS_SILVER


def test_silver_no_transforma_las_columnas_elegidas(cliente_bq, cfg_gcp, tabla_silver_tmp):
    """Cada columna de silver sale verbatim de precios_ext: sin derivar, sin filtrar."""
    tabla = _crear_silver(cliente_bq, cfg_gcp, tabla_silver_tmp)
    ext = cfg_gcp.tabla_bronce("precios_ext")
    cols = ", ".join(COLUMNAS_SILVER)

    diff = next(iter(cliente_bq.query(f"""
        SELECT
          (SELECT COUNT(*) FROM (SELECT {cols} FROM `{tabla}`
             EXCEPT DISTINCT SELECT {cols} FROM `{ext}`)) solo_silver,
          (SELECT COUNT(*) FROM (SELECT {cols} FROM `{ext}`
             EXCEPT DISTINCT SELECT {cols} FROM `{tabla}`)) solo_ext
    """).result()))

    assert diff["solo_silver"] == 0 and diff["solo_ext"] == 0


def test_silver_conserva_el_literal_del_scraper_en_tienda_raw(
    cliente_bq, cfg_gcp, tabla_silver_tmp
):
    """`tienda` es el slug; `tienda_raw` el valor crudo (número o nombre)."""
    tabla = _crear_silver(cliente_bq, cfg_gcp, tabla_silver_tmp)
    fila = next(iter(cliente_bq.query(f"""
        SELECT
          COUNT(DISTINCT tienda) slugs,
          COUNTIF(tienda_raw = '12' AND tienda = 'walmart') walmart_numerico
        FROM `{tabla}`
    """).result()))

    assert fila["slugs"] == 19
    assert fila["walmart_numerico"] > 0


def test_crear_tabla_silver_es_idempotente(cliente_bq, cfg_gcp, tabla_silver_tmp):
    tabla = _crear_silver(cliente_bq, cfg_gcp, tabla_silver_tmp)
    de_nuevo = _crear_silver(cliente_bq, cfg_gcp, tabla_silver_tmp)

    assert tabla == de_nuevo
    assert cliente_bq.get_table(tabla).num_rows == FILAS_HISTORICO
