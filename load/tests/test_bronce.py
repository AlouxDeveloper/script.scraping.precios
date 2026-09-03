"""El esquema de bronce: 26 columnas idénticas para las 6 variantes de entrada."""

import csv
import os
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from tests.conftest import esquema_y_filas

from precios_load.bronce import (
    COLUMNAS_BRONCE,
    ESQUEMA_BRONCE,
    FLAG_SOSPECHA_COPIA,
    a_tabla,
    ensamblar_archivo,
    md5_de_archivo,
)
from precios_load.config import ArchivoDeclarado

HEADER_V1 = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta",
    "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda",
]

# Una fila sana, una con precio centinela y una fila vacía.
FILAS = [
    ["900437", "https://heb.com.mx/x/p", "Cubrebocas", "41.90", "41.90",
     "https://img/1", "2026-06-14 20:31:07", "HEB"],
    ["N/A", "https://heb.com.mx/y/p", "Gasas", "No disponible", "",
     "https://img/2", "14/06/26 8:05", "12"],
    ["", "", "", "", "", "", "", ""],
]

RUTA = "2026/06_junio/scraping_detalle_heb.csv"

# Un archivo real por variante de header.
MUESTRAS = {
    "V1": "2025/diciembre/productos_detalle_fesa.csv",
    "V2": "2026/02_febrero/scraping_detalle_benavides.csv",
    "V3": "2026/02_febrero/scraping_detalle_guadalajara.csv",
    "V4": "2026/06_junio/scraping_detalle_heb.csv",
    "V5": "2026/06_junio/scraping_detalles_fahorro.csv",
    "V6": "2026/07_julio/scraping_detalle_chedraui.csv",
}

# Los 5 desfases de mes conocidos: filas desfasadas / filas del archivo.
DESFASES = {
    "2026/04_abril/scraping_detalle_walmart.csv": (35834, 35834),
    "2026/03_marzo/scraping_detalles_sanpablo.csv": (5937, 5937),
    "2026/06_junio/scraping_detalle_aurrera.csv": (732, 4822),
    "2026/01_enero/scraping_detalle_heb.csv": (8, 8),
    "2026/03_marzo/scraping_detalle_fesa.csv": (5, 7576),
}

FILAS_TOTAL = 995283


@pytest.fixture
def csv_v1(tmp_path):
    """Un CSV mínimo con header V1, escrito en un `salida/data` de mentira."""
    destino = tmp_path / os.path.dirname(RUTA)
    destino.mkdir(parents=True)
    with open(tmp_path / RUTA, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(HEADER_V1)
        escritor.writerows(FILAS)
    return tmp_path


def declarado(**extra) -> ArchivoDeclarado:
    base = {"ruta": RUTA, "tienda": "heb", "anio_mes": "2026-06"}
    return ArchivoDeclarado(**{**base, **extra})


# --- El esquema -------------------------------------------------------------


def test_las_26_columnas_en_orden(csv_v1):
    df = ensamblar_archivo(declarado(), base=str(csv_v1))
    assert list(df.columns) == list(COLUMNAS_BRONCE)
    assert len(COLUMNAS_BRONCE) == 26


def test_el_dataframe_es_1_a_1_con_el_csv(csv_v1):
    df = ensamblar_archivo(declarado(), base=str(csv_v1))
    assert len(df) == len(FILAS)


def test_la_fila_vacia_sigue_presente(csv_v1):
    df = ensamblar_archivo(declarado(), base=str(csv_v1))
    vacias = df[df["fila_vacia"]]
    assert len(vacias) == 1
    assert vacias.iloc[0]["_fila_num"] == 3


def test_la_tabla_arrow_usa_el_esquema_declarado(csv_v1):
    tabla = a_tabla(ensamblar_archivo(declarado(), base=str(csv_v1)))
    assert tabla.schema == ESQUEMA_BRONCE
    assert tabla.num_rows == len(FILAS)


def test_el_esquema_no_arrastra_metadata_de_pandas(csv_v1):
    tabla = a_tabla(ensamblar_archivo(declarado(), base=str(csv_v1)))
    assert tabla.schema.metadata is None


# --- Los valores originales nunca se pierden --------------------------------


RAWS = ("sku_raw", "precio_actual_raw", "precio_oferta_raw", "fecha_captura_raw", "tienda_raw")


def test_las_5_columnas_raw_siempre_estan_pobladas(csv_v1):
    """Incluso en la fila vacía: el literal es la cadena vacía, nunca un nulo."""
    df = ensamblar_archivo(declarado(), base=str(csv_v1))
    for columna in RAWS:
        assert df[columna].notna().all()
        assert df[columna].map(lambda v: isinstance(v, str)).all()


def test_el_raw_sobrevive_aunque_el_parseo_falle(csv_v1):
    df = ensamblar_archivo(declarado(), base=str(csv_v1))
    fila = df.iloc[1]

    assert pd.isna(fila["sku"]) and fila["sku_raw"] == "N/A"
    assert pd.isna(fila["precio_actual"]) and fila["precio_actual_raw"] == "No disponible"
    assert pd.isna(fila["precio_oferta"]) and fila["precio_oferta_raw"] == ""
    assert not fila["precio_parse_ok"]


def test_los_campos_de_negocio_se_parsean(csv_v1):
    fila = ensamblar_archivo(declarado(), base=str(csv_v1)).iloc[0]

    assert fila["sku"] == "900437"
    assert fila["precio_actual"] == Decimal("41.90")
    assert fila["fecha_captura"] == datetime(2026, 6, 14, 20, 31, 7, tzinfo=UTC)
    assert fila["producto"] == "Cubrebocas"
    assert fila["url_imagen"] == "https://img/1"
    assert list(fila["calidad_flags"]) == []


# --- Tienda: el slug manda, el literal se guarda ----------------------------


def test_la_tienda_viene_del_yaml_no_del_contenido(csv_v1):
    df = ensamblar_archivo(declarado(tienda="heb"), base=str(csv_v1))

    assert set(df["tienda"]) == {"heb"}
    # El mismo archivo escribe "HEB" y "12" en la columna del CSV.
    assert list(df["tienda_raw"]) == ["HEB", "12", ""]


def test_fesa_marzo_mezcla_dos_literales_bajo_un_solo_slug(datos_reales, por_ruta):
    """7,575 filas dicen `5` y 1 dice `Farmacias FESA`, en el mismo archivo."""
    df = ensamblar_archivo(por_ruta["2026/03_marzo/scraping_detalle_fesa.csv"], base=datos_reales)

    assert set(df["tienda"]) == {"fesa"}
    assert df["tienda_raw"].value_counts().to_dict() == {"5": 7575, "Farmacias FESA": 1}


# --- Linaje -----------------------------------------------------------------


def test_el_linaje_esta_poblado_en_todas_las_filas(csv_v1):
    momento = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    df = ensamblar_archivo(declarado(), base=str(csv_v1), ingestado_en=momento)

    assert set(df["_archivo_origen"]) == {RUTA}
    assert set(df["_variante_schema"]) == {"V1"}
    assert list(df["_fila_num"]) == [1, 2, 3]
    assert set(df["_ingestado_en"]) == {momento}
    assert set(df["_md5_origen"]) == {md5_de_archivo(str(csv_v1 / RUTA))}


def test_el_md5_cambia_si_el_archivo_cambia(csv_v1):
    ruta = str(csv_v1 / RUTA)
    antes = md5_de_archivo(ruta)
    with open(ruta, "a", encoding="utf-8") as f:
        f.write("1,,,,,,,\n")
    assert md5_de_archivo(ruta) != antes


# --- Desfase de mes ---------------------------------------------------------


def test_el_desfase_se_calcula_de_la_fecha_de_cada_fila(csv_v1):
    """El archivo es de junio; sus dos filas con fecha también, así que no hay desfase."""
    df = ensamblar_archivo(declarado(), base=str(csv_v1))
    assert list(df["anio_mes_dato"][:2]) == ["2026-06", "2026-06"]
    assert pd.isna(df["anio_mes_dato"].iloc[2])
    assert list(df["desfase_mes"]) == [False, False, False]


def test_una_fila_de_otro_mes_marca_desfase(csv_v1):
    """El caso de heb enero: el archivo está en una carpeta y sus fechas son de otro mes."""
    ruta_julio = "2026/07_julio/scraping_detalle_heb.csv"
    (csv_v1 / os.path.dirname(ruta_julio)).mkdir(parents=True)
    os.link(csv_v1 / RUTA, csv_v1 / ruta_julio)

    df = ensamblar_archivo(
        declarado(ruta=ruta_julio, anio_mes="2026-07"), base=str(csv_v1)
    )

    assert list(df["anio_mes"]) == ["2026-07"] * 3
    assert list(df["desfase_mes"]) == [True, True, False]


def test_sin_fecha_no_se_afirma_desfase(csv_v1):
    """La fila vacía no tiene mes con qué comparar: `desfase_mes` es False."""
    fila = ensamblar_archivo(declarado(), base=str(csv_v1)).iloc[2]
    assert pd.isna(fila["anio_mes_dato"])
    assert not fila["desfase_mes"]
    assert not fila["fecha_parse_ok"]


# --- Sospecha de copia ------------------------------------------------------


def test_la_sospecha_de_copia_marca_todas_las_filas(csv_v1):
    df = ensamblar_archivo(
        declarado(copia_de="2026/05_mayo/scraping_detalle_heb.csv"), base=str(csv_v1)
    )
    assert df["calidad_flags"].map(lambda f: FLAG_SOSPECHA_COPIA in f).all()


def test_sin_copia_declarada_no_aparece_el_flag(csv_v1):
    df = ensamblar_archivo(declarado(), base=str(csv_v1))
    assert not df["calidad_flags"].map(lambda f: FLAG_SOSPECHA_COPIA in f).any()


# --- Una muestra de cada variante -------------------------------------------


@pytest.mark.parametrize("variante,ruta", sorted(MUESTRAS.items()))
def test_cada_variante_produce_el_mismo_esquema(variante, ruta, datos_reales, por_ruta):
    df = ensamblar_archivo(por_ruta[ruta], base=datos_reales)
    tabla = a_tabla(df)

    assert tabla.schema == ESQUEMA_BRONCE
    assert set(df["_variante_schema"]) == {variante}
    assert list(df.columns) == list(COLUMNAS_BRONCE)


# --- El histórico completo --------------------------------------------------


def test_el_historico_completo_ensambla_1_a_1_con_el_mismo_esquema(datos_reales, declarados):
    """Un solo recorrido: filas, esquema y los 5 desfases conocidos."""
    filas = 0
    desfases = {}

    for d in declarados:
        df = ensamblar_archivo(d, base=datos_reales)
        _, esperadas = esquema_y_filas(datos_reales, d)

        assert len(df) == len(esperadas), d.ruta
        assert a_tabla(df).schema == ESQUEMA_BRONCE, d.ruta
        for columna in RAWS:
            assert df[columna].notna().all(), f"{d.ruta}: {columna}"

        filas += len(df)
        desfasadas = int(df["desfase_mes"].sum())
        if desfasadas:
            desfases[d.ruta] = (desfasadas, len(df))

    assert filas == FILAS_TOTAL
    assert desfases == DESFASES
