# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
#     "pyarrow",
#     "openpyxl",
# ]
# ///
"""Puente aportador: convierte el txt de `salida/catalogos` a Parquet.

Lee `Puentes por Aportador <corte>.txt` (6 columnas sin encabezado, separadas
por tabulador, codificación Latin-1) y agrega la columna `aportador` (nombre)
junto a la clave original, traducida con `CVE_APORTADOR_NOMBRE.xlsx`. Escribe
`salida/catalogos/puente_aportador.parquet`, todo-STRING (mismo criterio que
`load/src/precios_load/catalogos.py`: el origen ya es texto, tipar aquí
fijaría interpretaciones que se ven mejor en dbt).

No se aplica ningún otro cambio a los datos: sin dedup, sin filtrado, sin
volver a tipar `ndf_id`/`correlativo` (conservan ceros a la izquierda tal
cual vienen en el txt).

Se corre desde la raíz del repo:
    uv run scripts/generar_puente_aportador.py

Nota de contexto: `ndf_id` (7 dígitos) coincide en formato con `NDF` de
`dim_ndf.xlsx`, lo que sugiere que este archivo es el crosswalk
tienda-sku-ndf que `entity_resolution/` necesita (ver CLAUDE.md, sección de
`transform/`, "Pendiente"). Esto es una observación, no una validación: el
nombre de columna se puso así por decisión explícita, confirmar el cruce real
es tarea de `entity_resolution/`, todavía sin empezar.
"""

from __future__ import annotations

import csv
import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Rutas relativas a la raíz del repo, igual que el resto de los scripts.
RUTA_TXT = "./salida/catalogos/Puentes por Aportador 260910.txt"
RUTA_XLSX = "./salida/catalogos/CVE_APORTADOR_NOMBRE.xlsx"
RUTA_SALIDA = "./salida/catalogos/puente_aportador.parquet"

# El txt no trae encabezado; nombres por posición según la inspección manual
# del archivo (ver docstring del módulo).
COLUMNAS_TXT = (
    "aportador_clave",
    "bandera",
    "correlativo",
    "ndf_id",
    "producto",
    "descripcion",
)

# Orden final del Parquet: la traducción va junto a la clave que traduce.
COLUMNAS_SALIDA = (
    "aportador_clave",
    "aportador",
    "bandera",
    "correlativo",
    "ndf_id",
    "producto",
    "descripcion",
)

ESQUEMA_PUENTE = pa.schema([(nombre, pa.string()) for nombre in COLUMNAS_SALIDA])


def leer_mapa_aportador(ruta: str = RUTA_XLSX) -> dict[str, str]:
    """Lee el XLSX de claves y devuelve el mapa clave -> nombre de aportador.

    `dtype=str` evita que pandas convierta claves puramente numéricas (22,
    89) a float; `.str.strip()` quita el espacio final que trae alguna clave
    en el origen (`"I4 "`).
    """
    mapa = pd.read_excel(ruta, dtype=str)
    claves = mapa.iloc[:, 0].str.strip()
    nombres = mapa.iloc[:, 1]
    return dict(zip(claves, nombres))


def leer_puentes(ruta: str = RUTA_TXT) -> pd.DataFrame:
    """Lee el txt de puentes tal cual, sin tipar ni deduplicar.

    `quoting=csv.QUOTE_NONE`: 663 líneas del archivo traen una comilla suelta
    dentro de `descripcion` (no es un campo entrecomillado). Con el quoting
    por defecto, pandas las interpreta como inicio de campo y fusiona varias
    líneas físicas en un solo registro — se pierden ~50 mil filas sin avisar.
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
    df = df.copy()
    df["aportador"] = df["aportador_clave"].map(mapa)
    faltantes = sorted(
        df.loc[df["aportador"].isna(), "aportador_clave"].unique()
    )
    return df[list(COLUMNAS_SALIDA)], faltantes


def a_parquet(df: pd.DataFrame) -> pa.Table:
    """Convierte el DataFrame al esquema fijo del puente, todo STRING."""
    limpio = df.astype(object).where(pd.notna(df), None)
    tabla = pa.Table.from_pandas(limpio, schema=ESQUEMA_PUENTE, preserve_index=False)
    return tabla.replace_schema_metadata(None)


def main() -> None:
    mapa = leer_mapa_aportador()
    df = leer_puentes()
    df, faltantes = traducir_aportador(df, mapa)

    os.makedirs(os.path.dirname(RUTA_SALIDA), exist_ok=True)
    pq.write_table(a_parquet(df), RUTA_SALIDA, compression="snappy")

    print(f"✅ {len(df)} filas escritas en {RUTA_SALIDA}")
    if faltantes:
        conteo = df[df["aportador_clave"].isin(faltantes)][
            "aportador_clave"
        ].value_counts()
        print(f"⚠️  {len(faltantes)} claves sin traducción en el xlsx:")
        for clave in faltantes:
            print(f"   {clave}: {conteo[clave]} filas")
    else:
        print("✅ Todas las claves de aportador se tradujeron.")


if __name__ == "__main__":
    main()
