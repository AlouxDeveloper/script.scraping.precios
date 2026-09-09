"""El catálogo NDF: XLSX de 23 columnas -> Parquet de 17, todo STRING."""

import os
from dataclasses import replace

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from precios_load import catalogos
from precios_load.cli import app
from precios_load.catalogos import (
    COLUMNAS_DESCARTADAS,
    COLUMNAS_NDF,
    ESQUEMA_NDF,
    HOJA,
    RENOMBRE,
    ErrorColumnaDesconocida,
    a_parquet,
    a_tabla,
    leer_xlsx,
)
from precios_load.config import cargar_config

# Hechos del archivo real, verificados en el issue ALD-39.
FILAS_ESPERADAS = 180914
COLUMNAS_ESPERADAS = 17


@pytest.fixture(scope="module")
def xlsx_ndf() -> str:
    """Ruta al XLSX real del NDF, o salta si no está en esta máquina."""
    ruta = os.path.join(cargar_config().ruta_catalogos(), catalogos.NOMBRE_XLSX)
    if not os.path.isfile(ruta):
        pytest.skip("salida/catalogos/dim_ndf.xlsx no existe en esta máquina")
    return ruta


@pytest.fixture(scope="module")
def df_ndf(xlsx_ndf) -> pd.DataFrame:
    return leer_xlsx(xlsx_ndf)


def test_el_mapa_tiene_las_17_columnas_del_modelo():
    assert len(RENOMBRE) == COLUMNAS_ESPERADAS
    assert COLUMNAS_NDF == tuple(RENOMBRE.values())
    assert ESQUEMA_NDF.names == list(RENOMBRE.values())
    assert all(campo.type == pa.string() for campo in ESQUEMA_NDF)


def test_leer_xlsx_devuelve_17_columnas_renombradas(df_ndf):
    assert list(df_ndf.columns) == list(COLUMNAS_NDF)
    assert len(df_ndf) == FILAS_ESPERADAS


def test_ndf_id_es_pk_sin_dedup_previo(df_ndf):
    """`ndf_id` es único en el archivo entero: sirve de PK tal cual."""
    assert df_ndf["ndf_id"].is_unique
    assert df_ndf["ndf_id"].notna().all()


def test_las_sales_no_llegan_al_parquet(df_ndf):
    for descartada in COLUMNAS_DESCARTADAS:
        assert descartada not in df_ndf.columns


def test_a_tabla_fija_el_esquema_todo_string(df_ndf):
    tabla = a_tabla(df_ndf)

    assert tabla.schema == ESQUEMA_NDF
    assert tabla.num_rows == FILAS_ESPERADAS
    assert tabla.num_columns == COLUMNAS_ESPERADAS
    assert tabla.schema.metadata is None


def test_a_parquet_roundtrip(df_ndf):
    tabla = pq.read_table(pa.BufferReader(a_parquet(df_ndf)))

    assert tabla.num_rows == FILAS_ESPERADAS
    assert [t for t in tabla.schema.types] == [pa.string()] * COLUMNAS_ESPERADAS


# --- Fallo ante un XLSX inesperado ----------------------------------------


def _xlsx_temporal(tmp_path, columnas: list[str]) -> str:
    """Deja un XLSX mínimo con la hoja real y las columnas pedidas."""
    ruta = str(tmp_path / "dim_ndf.xlsx")
    pd.DataFrame([{c: "x" for c in columnas}]).to_excel(
        ruta, sheet_name=HOJA, index=False
    )
    return ruta


def test_renombrado_23_a_17_descarta_las_sales(tmp_path):
    """Un XLSX con las 23 del origen da las 17 del modelo, sin las seis Cve Sal."""
    ruta = _xlsx_temporal(tmp_path, list(RENOMBRE) + list(COLUMNAS_DESCARTADAS))

    df = leer_xlsx(ruta)

    assert list(df.columns) == list(COLUMNAS_NDF)
    assert len(df.columns) == COLUMNAS_ESPERADAS
    for descartada in COLUMNAS_DESCARTADAS:
        assert descartada not in df.columns


def test_ndf_id_con_cero_a_la_izquierda_sobrevive_el_roundtrip(tmp_path):
    """El contrato con Knobloch: `00123` no se vuelve `123`, ni `190012` un entero.

    `ndf_id` y `fecha_lanzamiento` parecen numéricos; el Parquet los conserva
    como texto para que el cero a la izquierda y el `YYYYMM` lleguen intactos.
    """
    fila = {c: "x" for c in list(RENOMBRE) + list(COLUMNAS_DESCARTADAS)}
    fila["NDF"] = "00123"
    fila["Fecha Lanz"] = "190012"
    ruta = str(tmp_path / "dim_ndf.xlsx")
    pd.DataFrame([fila]).to_excel(ruta, sheet_name=HOJA, index=False)

    tabla = pq.read_table(pa.BufferReader(a_parquet(leer_xlsx(ruta))))

    assert tabla.schema.field("ndf_id").type == pa.string()
    assert tabla.schema.field("fecha_lanzamiento").type == pa.string()
    assert tabla.column("ndf_id").to_pylist() == ["00123"]
    assert tabla.column("fecha_lanzamiento").to_pylist() == ["190012"]


def test_columna_desconocida_detiene_la_carga(tmp_path):
    ruta = _xlsx_temporal(tmp_path, list(RENOMBRE) + ["Columna Nueva"])

    with pytest.raises(ErrorColumnaDesconocida, match="Columna Nueva"):
        leer_xlsx(ruta)


def test_columna_faltante_detiene_la_carga(tmp_path):
    ruta = _xlsx_temporal(tmp_path, list(RENOMBRE)[:-1])

    with pytest.raises(ErrorColumnaDesconocida, match="División"):
        leer_xlsx(ruta)


# --- Comando del CLI ------------------------------------------------------

runner = CliRunner()


def test_comando_aborta_si_no_hay_xlsx(tmp_path, monkeypatch):
    """Sin el XLSX, mensaje claro en vez de un stack trace de pandas."""
    cfg = replace(cargar_config(), ruta_local_catalogos=str(tmp_path))
    monkeypatch.setattr("precios_load.cli.cargar_config", lambda: cfg)

    resultado = runner.invoke(app, ["catalogos"])

    assert resultado.exit_code == 1
    assert "No se encontró el catálogo" in resultado.output


def test_comando_aborta_fuera_de_la_raiz_del_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    resultado = runner.invoke(app, ["catalogos"])

    assert resultado.exit_code != 0
    assert "raíz del repo" in resultado.output
