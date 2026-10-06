"""El puente aportador: TXT+XLSX de Knobloch -> Parquet de 7 columnas, todo STRING."""

import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from precios_load import puente_aportador
from precios_load.cli import app
from precios_load.config import cargar_config
from precios_load.puente_aportador import (
    COLUMNAS_PUENTE,
    COLUMNAS_TXT,
    ESQUEMA_PUENTE,
    a_parquet,
    a_tabla,
    leer_mapa_aportador,
    leer_txt,
    traducir_aportador,
)

# Hechos del archivo real, verificados a mano sobre el corte 260910.
FILAS_ESPERADAS = 952_605
COLUMNAS_ESPERADAS = 7


@pytest.fixture(scope="module")
def rutas_reales() -> tuple[str, str]:
    """Rutas al TXT y al XLSX reales, o salta si no están en esta máquina."""
    base = cargar_config().ruta_catalogos()
    ruta_txt = os.path.join(base, puente_aportador.NOMBRE_TXT)
    ruta_xlsx = os.path.join(base, puente_aportador.NOMBRE_XLSX_APORTADORES)
    if not os.path.isfile(ruta_txt) or not os.path.isfile(ruta_xlsx):
        pytest.skip(
            "salida/catalogos/puente_aportador.txt o "
            "CVE_APORTADOR_NOMBRE.xlsx no existen en esta máquina"
        )
    return ruta_txt, ruta_xlsx


@pytest.fixture(scope="module")
def df_puente(rutas_reales) -> pd.DataFrame:
    ruta_txt, ruta_xlsx = rutas_reales
    df, _ = traducir_aportador(leer_txt(ruta_txt), leer_mapa_aportador(ruta_xlsx))
    return df


def test_el_esquema_tiene_las_7_columnas_del_modelo():
    assert len(COLUMNAS_PUENTE) == COLUMNAS_ESPERADAS
    assert ESQUEMA_PUENTE.names == list(COLUMNAS_PUENTE)
    assert all(campo.type == pa.string() for campo in ESQUEMA_PUENTE)


def test_leer_txt_devuelve_las_6_columnas_de_origen(rutas_reales):
    ruta_txt, _ = rutas_reales
    df = leer_txt(ruta_txt)

    assert list(df.columns) == list(COLUMNAS_TXT)
    assert len(df) == FILAS_ESPERADAS


def test_traducir_aportador_agrega_la_columna_junto_a_la_clave(df_puente):
    assert list(df_puente.columns) == list(COLUMNAS_PUENTE)
    assert len(df_puente) == FILAS_ESPERADAS


def test_a_tabla_fija_el_esquema_todo_string(df_puente):
    tabla = a_tabla(df_puente)

    assert tabla.schema == ESQUEMA_PUENTE
    assert tabla.num_rows == FILAS_ESPERADAS
    assert tabla.num_columns == COLUMNAS_ESPERADAS
    assert tabla.schema.metadata is None


def test_a_parquet_roundtrip(df_puente):
    tabla = pq.read_table(pa.BufferReader(a_parquet(df_puente)))

    assert tabla.num_rows == FILAS_ESPERADAS
    assert [t for t in tabla.schema.types] == [pa.string()] * COLUMNAS_ESPERADAS


# --- Traducción de aportador, con datos sintéticos -------------------------


def test_clave_sin_traducir_queda_nula_y_se_reporta():
    df = pd.DataFrame(
        [
            {
                "aportador_clave": "X9",
                "bandera": "1",
                "correlativo": "000000000123456",
                "ndf_id": "1053003",
                "producto": "ALGO",
                "descripcion": "ALGO EN CAJA",
            }
        ]
    )

    resultado, faltantes = traducir_aportador(df, mapa={})

    assert faltantes == ["X9"]
    assert resultado["aportador"].isna().all()


def test_clave_traducida_no_aparece_en_faltantes():
    df = pd.DataFrame(
        [
            {
                "aportador_clave": "N0",
                "bandera": "1",
                "correlativo": "000000000123456",
                "ndf_id": "1053003",
                "producto": "ALGO",
                "descripcion": "ALGO EN CAJA",
            }
        ]
    )

    resultado, faltantes = traducir_aportador(df, mapa={"N0": "SORIANA (MERCADO)"})

    assert faltantes == []
    assert resultado["aportador"].tolist() == ["SORIANA (MERCADO)"]


def test_correlativo_con_cero_a_la_izquierda_sobrevive_el_roundtrip():
    """El contrato con Knobloch: `000000000123456` no se vuelve un entero."""
    df = pd.DataFrame(
        [
            {
                "aportador_clave": "N0",
                "bandera": "1",
                "correlativo": "000000000123456",
                "ndf_id": "0108020",
                "producto": "X",
                "descripcion": "Y",
            }
        ]
    )
    resultado, _ = traducir_aportador(df, mapa={"N0": "SORIANA (MERCADO)"})

    tabla = pq.read_table(pa.BufferReader(a_parquet(resultado)))

    assert tabla.schema.field("correlativo").type == pa.string()
    assert tabla.schema.field("ndf_id").type == pa.string()
    assert tabla.column("correlativo").to_pylist() == ["000000000123456"]
    assert tabla.column("ndf_id").to_pylist() == ["0108020"]


# --- Comando del CLI ---------------------------------------------------


runner = CliRunner()


def test_comando_aborta_si_no_hay_txt_ni_xlsx(tmp_path, monkeypatch):
    """Sin los archivos de origen, mensaje claro en vez de un stack trace de pandas."""
    from dataclasses import replace

    cfg = replace(cargar_config(), ruta_local_catalogos=str(tmp_path))
    monkeypatch.setattr("precios_load.cli.cargar_config", lambda: cfg)

    resultado = runner.invoke(app, ["catalogos-puente"])

    assert resultado.exit_code == 1
    assert "No se encontró" in resultado.output


def test_comando_aborta_fuera_de_la_raiz_del_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    resultado = runner.invoke(app, ["catalogos-puente"])

    assert resultado.exit_code != 0
    assert "raíz del repo" in resultado.output
