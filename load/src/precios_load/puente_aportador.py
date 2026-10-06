"""Puente aportador: crosswalk tienda-sku-ndf, de TXT+XLSX a Parquet para bronce.

Convierte `salida/catalogos/puente_aportador.txt` (6 columnas sin encabezado,
separadas por tabulador, Latin-1) más `CVE_APORTADOR_NOMBRE.xlsx` (traducción
de clave de aportador a nombre) en un Parquet de 7 columnas todo-STRING. Lo
dispara el comando `catalogos-puente` del CLI; no forma parte de `ingesta` ni
de `catalogos` (NDF) — es un tercer catálogo independiente.

Es el crosswalk que `entity_resolution/` (en `transform/`) documenta como
pendiente: `ndf_id` es la llave del catálogo NDF y `aportador_clave`
identifica la tienda vía la columna del mismo nombre en el seed `dim_tienda`.
`correlativo` NO coincide con el sku que escriben los scrapers (validado en
dbt: 0-14% de match según tienda, parece un identificador propio del
aportador) — el entity resolution real va a necesitar matching por texto,
no un join por sku. El join contra `dim_producto`/`fact_precios` no se hace
aquí — este módulo solo deja el dato disponible en bronce; el resto es
trabajo de dbt.

**Sin manifest de idempotencia**, mismo criterio que `catalogos.py`: es un
snapshot de reemplazo completo, no una serie append-only, así que correr el
comando dos veces sobrescribe el mismo objeto en bronce.

**Todo el Parquet va en STRING**, a propósito: el origen ya es texto y tipar
aquí (quitar el cero a la izquierda de `correlativo`, por ejemplo) fijaría una
interpretación que se ve mejor en dbt.

`bandera` se lee y se conserva en el Parquet, fiel al origen, pero no entra al
modelo de matching — se descarta en `stg_puente_aportador` de dbt, no aquí.
"""

from __future__ import annotations

import csv
import io
import os
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from precios_load.clientes import REINTENTO_SUBIDA
from precios_load.config import ConfigGCP

if TYPE_CHECKING:
    from google.cloud import storage

# El txt no trae encabezado; nombres por posición según la inspección manual
# del archivo.
COLUMNAS_TXT = (
    "aportador_clave",
    "bandera",
    "correlativo",
    "ndf_id",
    "producto",
    "descripcion",
)

# Orden final del Parquet: la traducción va junto a la clave que traduce.
COLUMNAS_PUENTE = (
    "aportador_clave",
    "aportador",
    "bandera",
    "correlativo",
    "ndf_id",
    "producto",
    "descripcion",
)

ESQUEMA_PUENTE = pa.schema([(nombre, pa.string()) for nombre in COLUMNAS_PUENTE])

# Objeto del catálogo dentro del prefijo de catálogos de la capa bronce.
NOMBRE_BRONCE = "puente_aportador/puente_aportador.parquet"

# Archivos de origen dentro de `salida/catalogos`. El TXT trae el corte en el
# nombre real (`Puentes por Aportador <fecha>.txt`); igual que `dim_ndf.xlsx`,
# se espera un nombre fijo sin fecha — Aldo reemplaza el archivo cada corte.
NOMBRE_TXT = "puente_aportador.txt"
NOMBRE_XLSX_APORTADORES = "CVE_APORTADOR_NOMBRE.xlsx"


def leer_mapa_aportador(ruta: str) -> dict[str, str]:
    """Lee el XLSX de claves y devuelve el mapa clave -> nombre de aportador.

    `dtype=str` evita que pandas convierta claves puramente numéricas (`22`,
    `89`) a float; `.str.strip()` quita el espacio final que trae alguna clave
    en el origen (`"I4 "`).
    """
    mapa = pd.read_excel(ruta, dtype=str)
    claves = mapa.iloc[:, 0].str.strip()
    nombres = mapa.iloc[:, 1]
    return dict(zip(claves, nombres))


def leer_txt(ruta: str) -> pd.DataFrame:
    """Lee el txt de puentes tal cual, sin tipar ni deduplicar.

    `quoting=csv.QUOTE_NONE`: varias líneas del archivo traen una comilla
    suelta dentro de `descripcion` (no es un campo entrecomillado). Con el
    quoting por defecto, pandas las interpreta como inicio de campo y fusiona
    varias líneas físicas en un solo registro, perdiendo filas sin avisar.
    """
    return pd.read_csv(
        ruta,
        sep="\t",
        header=None,
        names=COLUMNAS_TXT,
        dtype=str,
        encoding="latin-1",
        quoting=csv.QUOTE_NONE,
    )


def traducir_aportador(
    df: pd.DataFrame, mapa: dict[str, str]
) -> tuple[pd.DataFrame, list[str]]:
    """Agrega la columna `aportador` y devuelve las claves sin traducción.

    Las claves que no están en `mapa` quedan con `aportador` nulo en vez de
    detener la conversión: el txt es un archivo de terceros y puede traer
    claves que el xlsx de traducción todavía no cubre.
    """
    con_aportador = df.copy()
    con_aportador["aportador"] = con_aportador["aportador_clave"].map(mapa)
    faltantes = sorted(
        con_aportador.loc[con_aportador["aportador"].isna(), "aportador_clave"].unique()
    )
    return con_aportador[list(COLUMNAS_PUENTE)], faltantes


def a_tabla(df: pd.DataFrame) -> pa.Table:
    """Convierte el DataFrame al esquema fijo del puente, todo STRING.

    Mismo criterio que `catalogos.a_tabla`: NaN a nulo (no al texto `'nan'`) y
    sin la metadata que pandas inyecta, para reproducibilidad byte a byte.
    """
    limpio = df.astype(object).where(pd.notna(df), None)
    tabla = pa.Table.from_pandas(limpio, schema=ESQUEMA_PUENTE, preserve_index=False)
    return tabla.replace_schema_metadata(None)


def a_parquet(df: pd.DataFrame) -> bytes:
    """Serializa el DataFrame al Parquet snappy en memoria."""
    buffer = io.BytesIO()
    pq.write_table(a_tabla(df), buffer, compression="snappy")
    return buffer.getvalue()


def escribir(
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    ruta_txt: str | None = None,
    ruta_xlsx: str | None = None,
) -> tuple[str, int, list[str]]:
    """Convierte el TXT+XLSX locales y sube el Parquet a la capa bronce.

    Devuelve la URI del objeto, el número de filas y las claves de aportador
    sin traducir (si las hay). El objeto se sobrescribe en sitio: snapshot de
    reemplazo, sin particiones hive ni versiones, igual que `catalogos.escribir`.
    """
    if ruta_txt is None:
        ruta_txt = os.path.join(config.ruta_catalogos(), NOMBRE_TXT)
    if ruta_xlsx is None:
        ruta_xlsx = os.path.join(config.ruta_catalogos(), NOMBRE_XLSX_APORTADORES)

    mapa = leer_mapa_aportador(ruta_xlsx)
    df, faltantes = traducir_aportador(leer_txt(ruta_txt), mapa)

    datos = a_parquet(df)
    filas = pq.read_metadata(io.BytesIO(datos)).num_rows

    uri = config.uri_bronce_catalogo(NOMBRE_BRONCE)
    objeto = uri.removeprefix(f"gs://{config.bucket_bronce}/")
    blob = cliente_gcs.bucket(config.bucket_bronce).blob(objeto)
    blob.upload_from_string(
        datos,
        content_type="application/vnd.apache.parquet",
        retry=REINTENTO_SUBIDA,
    )
    return uri, filas, faltantes
