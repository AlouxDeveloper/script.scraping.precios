"""Catálogo NDF: el XLSX de un mes a un Parquet todo-STRING para bronce.

Convierte `salida/catalogos/dim_ndf.xlsx` (una hoja, 23 columnas) en un Parquet
de 17 columnas renombradas a `snake_case` sin acentos. Se corre a mano cuando
llega una versión nueva del catálogo; no forma parte de `ingesta`.

**Todo el Parquet va en STRING, a propósito.** El origen ya es texto y no hay
parsers frágiles que auditar. Tipar aquí fijaría interpretaciones que se ven
mejor en dbt: `ndf_id` llega sin cero a la izquierda (1 a 7 dígitos) y
`fecha_lanzamiento` es un `YYYYMM` de seis caracteres, no una fecha (`190012` es
centinela). Por eso este módulo no replica el patrón `*_raw` de `bronce.py`:
aquí el valor original *es* el valor.

`Cve Sal1`..`Cve Sal6` (centinela `99999`) existen en el XLSX pero se descartan
por decisión de alcance: las sales no entran en el modelo de matching. No es un
olvido; si un día se necesitan, se añaden a `RENOMBRE`.

Con un solo catálogo las constantes viven aquí. Al segundo se extrae un
`catalogos.yml` declarativo, como `archivos.yml` para el histórico.
"""

from __future__ import annotations

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

# Nombre de la única hoja del XLSX. El título lleva el mes del corte
# ("... Jul 2026"): si deja de coincidir es que llegó un catálogo nuevo y hay
# que revisar que las columnas sigan siendo las mismas antes de recargar.
HOJA = "Farma&No Farma Data Jul 2026"

# Origen -> modelo. El orden de este mapa es el orden de columnas del Parquet.
# Toda columna del XLSX tiene que estar aquí o en COLUMNAS_DESCARTADAS; una que
# no aparezca en ninguna de las dos detiene la carga (ver `leer_xlsx`).
RENOMBRE = {
    "Fecha Lanz": "fecha_lanzamiento",
    "NDF": "ndf_id",
    "Presentación": "presentacion",
    "Producto": "producto",
    "Descripción": "descripcion",
    "Cve Lab": "cve_laboratorio",
    "Laboratorio": "laboratorio",
    "Corporación": "corporacion",
    "Cve Mg": "cve_mg",
    "Cve Gen": "cve_genero",
    "Género": "genero",
    "Cve Ct": "cve_ct",
    "FF": "cve_ff",
    "Forma Farmacéutica 3": "forma_farmaceutica_n3",
    "Std Fac": "std_fac",
    "Molécula": "molecula",
    "División": "division",
}

# Las seis columnas de sales, con centinela `99999`. Se leen y se tiran: el
# matching contra el catálogo no las usa. Se listan aquí para que quede claro
# que la ausencia en el Parquet es deliberada, no un descuido.
COLUMNAS_DESCARTADAS = (
    "Cve Sal1",
    "Cve Sal2",
    "Cve Sal3",
    "Cve Sal4",
    "Cve Sal5",
    "Cve Sal6",
)

# Esquema del Parquet: las 17 columnas del modelo, todas STRING.
ESQUEMA_NDF = pa.schema([(nombre, pa.string()) for nombre in RENOMBRE.values()])

COLUMNAS_NDF = tuple(ESQUEMA_NDF.names)

# Objeto del catálogo dentro del prefijo de catálogos de la capa bronce.
NOMBRE_BRONCE = "ndf/dim_ndf.parquet"

# Archivo de origen dentro de `salida/catalogos`.
NOMBRE_XLSX = "dim_ndf.xlsx"


class ErrorColumnaDesconocida(Exception):
    """El XLSX no tiene las columnas previstas.

    O trae una que no está en `RENOMBRE` ni en `COLUMNAS_DESCARTADAS`, o le
    falta una del mapa. Se detiene la carga en vez de escribir un Parquet con
    el modelo incompleto y que nadie lo note.
    """


def leer_xlsx(ruta: str, hoja: str = HOJA) -> pd.DataFrame:
    """Lee el XLSX del NDF y devuelve el DataFrame de 17 columnas.

    Todo se lee como texto (`dtype=str`) para no perder ceros a la izquierda si
    un export futuro los trae. Las filas no se filtran ni se deduplican: `ndf_id`
    ya es único en el archivo real (verificado, 180,914 filas), y cualquier
    saneo posterior es cosa de dbt.
    """
    df = pd.read_excel(ruta, sheet_name=hoja, dtype=str)

    conocidas = set(RENOMBRE) | set(COLUMNAS_DESCARTADAS)
    desconocidas = [c for c in df.columns if c not in conocidas]
    if desconocidas:
        raise ErrorColumnaDesconocida(
            f"{ruta}: la hoja '{hoja}' trae columnas no previstas: "
            f"{', '.join(map(repr, desconocidas))}. "
            f"Agrégalas a RENOMBRE o a COLUMNAS_DESCARTADAS en catalogos.py."
        )

    faltantes = [c for c in RENOMBRE if c not in df.columns]
    if faltantes:
        raise ErrorColumnaDesconocida(
            f"{ruta}: la hoja '{hoja}' no trae las columnas esperadas: "
            f"{', '.join(map(repr, faltantes))}."
        )

    return df[list(RENOMBRE)].rename(columns=RENOMBRE)


def a_tabla(df: pd.DataFrame) -> pa.Table:
    """Convierte el DataFrame al esquema fijo del NDF, todo STRING.

    Las celdas vacías (`NaN` que mete pandas) se pasan a nulo, no al texto
    `'nan'`. Se descarta la metadata que pandas inyecta, igual que en
    `bronce.a_tabla`, para que dos corridas del mismo XLSX den el mismo Parquet.
    """
    limpio = df.astype(object).where(pd.notna(df), None)
    tabla = pa.Table.from_pandas(limpio, schema=ESQUEMA_NDF, preserve_index=False)
    return tabla.replace_schema_metadata(None)


def a_parquet(df: pd.DataFrame) -> bytes:
    """Serializa el DataFrame al Parquet snappy en memoria.

    Mismo estilo que `bronce.escribir`: buffer en memoria, sin archivo temporal.
    """
    buffer = io.BytesIO()
    pq.write_table(a_tabla(df), buffer, compression="snappy")
    return buffer.getvalue()


def escribir(
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    ruta_local: str | None = None,
) -> tuple[str, int]:
    """Convierte el XLSX local y sube el Parquet a la capa bronce de catálogos.

    Devuelve la URI del objeto y el número de filas escritas. El objeto se
    sobrescribe en sitio: un catálogo es un snapshot de reemplazo, no una serie
    temporal, así que no lleva particiones hive ni versiones. El PUT de GCS es
    atómico, igual que en bronce.
    """
    if ruta_local is None:
        ruta_local = os.path.join(config.ruta_catalogos(), NOMBRE_XLSX)

    datos = a_parquet(leer_xlsx(ruta_local))
    filas = pq.read_metadata(io.BytesIO(datos)).num_rows

    uri = config.uri_bronce_catalogo(NOMBRE_BRONCE)
    objeto = uri.removeprefix(f"gs://{config.bucket_bronce}/")
    blob = cliente_gcs.bucket(config.bucket_bronce).blob(objeto)
    blob.upload_from_string(
        datos,
        content_type="application/vnd.apache.parquet",
        retry=REINTENTO_SUBIDA,
    )
    return uri, filas
