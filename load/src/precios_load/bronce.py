"""Ensamblado de la capa bronce: un CSV del histórico -> un DataFrame tipado.

Integra los parsers de `normalizacion` en un esquema único, idéntico para las
139 particiones y para las 6 variantes de header de entrada.

Principio rector: **nunca se pierde el valor original**. Cada campo derivado
convive con su `_raw`, así que un bug en un parser se corrige regenerando
bronce, sin volver a tocar la capa raw.

Dos reglas que no se ven en el esquema:

- `tienda` es el slug de `archivos.yml`, nunca el contenido del CSV. La columna
  del origen es un caos: 31 valores distintos, alterna nombre e ID numérico
  según el mes (Chedraui es `15` en febrero y `Chedraui` el resto del año) y
  FESA mezcla `5` y `Farmacias FESA` dentro del mismo archivo. El literal se
  conserva en `tienda_raw`.
- `anio_mes` sale de la carpeta de origen; `anio_mes_dato`, de la fecha de cada
  fila. Cuando difieren, `desfase_mes = True`.
"""

import csv
import hashlib
import os
from datetime import UTC, datetime

import pandas as pd
import pyarrow as pa

from precios_load.config import ArchivoDeclarado, cargar_config
from precios_load.esquemas import Esquema, detectar
from precios_load.normalizacion import normalizar_fila

# Flag de los archivos que `archivos.yml` marca como sospechosos de ser copia
# de un mes anterior.
FLAG_SOSPECHA_COPIA = "SOSPECHA_COPIA"

# Columnas de paso: se copian del CSV sin normalizar.
COLUMNAS_TEXTO = ("url_producto", "producto", "url_imagen")

# El esquema de bronce, en el orden en que viaja a Parquet y a BigQuery.
#
# `fecha_captura` se marca como UTC para que BigQuery lo lea como TIMESTAMP y
# no como DATETIME. El histórico no trae zona horaria en ningún formato, así
# que se conserva la hora de pared tal cual la escribió el scraper.
ESQUEMA_BRONCE = pa.schema(
    [
        # Partición (hive, viene de la ruta)
        ("tienda", pa.string()),
        ("anio_mes", pa.string()),
        # Negocio
        ("sku", pa.string()),
        ("url_producto", pa.string()),
        ("producto", pa.string()),
        ("url_imagen", pa.string()),
        ("precio_actual", pa.decimal128(38, 9)),
        ("precio_oferta", pa.decimal128(38, 9)),
        ("fecha_captura", pa.timestamp("us", tz="UTC")),
        # Valores originales
        ("sku_raw", pa.string()),
        ("precio_actual_raw", pa.string()),
        ("precio_oferta_raw", pa.string()),
        ("fecha_captura_raw", pa.string()),
        ("tienda_raw", pa.string()),
        # Calidad
        ("calidad_flags", pa.list_(pa.string())),
        ("precio_parse_ok", pa.bool_()),
        ("fecha_parse_ok", pa.bool_()),
        ("sku_es_centinela", pa.bool_()),
        ("fila_vacia", pa.bool_()),
        ("desfase_mes", pa.bool_()),
        ("anio_mes_dato", pa.string()),
        # Linaje
        ("_archivo_origen", pa.string()),
        ("_md5_origen", pa.string()),
        ("_variante_schema", pa.string()),
        ("_fila_num", pa.int64()),
        ("_ingestado_en", pa.timestamp("us", tz="UTC")),
    ]
)

COLUMNAS_BRONCE = tuple(ESQUEMA_BRONCE.names)


def md5_de_archivo(ruta: str) -> str:
    """MD5 del CSV de origen, para el linaje y para detectar recargas."""
    digest = hashlib.md5()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def ensamblar_archivo(
    declarado: ArchivoDeclarado,
    base: str | None = None,
    ingestado_en: datetime | None = None,
) -> pd.DataFrame:
    """Lee un CSV del histórico y devuelve su DataFrame de bronce.

    El resultado es 1:1 en filas con el CSV: ninguna fila se descarta, ni
    siquiera las 150 completamente vacías. Bronce tiene que reconciliar
    conteos contra raw; el filtrado es cosa de silver.
    """
    base = base if base is not None else cargar_config().ruta_datos()
    ruta_csv = os.path.join(base, declarado.ruta)
    ingestado_en = ingestado_en or datetime.now(UTC)
    md5 = md5_de_archivo(ruta_csv)

    with open(ruta_csv, encoding="utf-8", errors="replace", newline="") as f:
        lector = csv.reader(f)
        cabecera = None if declarado.sin_header else next(lector, None)
        esquema = detectar(declarado, cabecera)
        registros = [
            _registro(declarado, esquema, fila, numero, md5, ingestado_en)
            for numero, fila in enumerate(lector, start=1)
        ]

    return pd.DataFrame(registros, columns=list(COLUMNAS_BRONCE))


def a_tabla(df: pd.DataFrame) -> pa.Table:
    """Convierte el DataFrame al esquema fijo de bronce.

    Es lo que garantiza que las 6 variantes de header produzcan exactamente el
    mismo Parquet: el esquema es el declarado aquí, no el que pandas infiera de
    los datos de un archivo concreto. Se descarta además la metadata que pandas
    inyecta, que cambia según el archivo y ensuciaría la comparación.
    """
    tabla = pa.Table.from_pandas(df, schema=ESQUEMA_BRONCE, preserve_index=False)
    return tabla.replace_schema_metadata(None)


def _registro(
    declarado: ArchivoDeclarado,
    esquema: Esquema,
    fila: list[str],
    numero: int,
    md5: str,
    ingestado_en: datetime,
) -> dict:
    """Una fila del CSV convertida a las 26 columnas de bronce."""
    n = normalizar_fila(esquema, fila)

    anio_mes_dato = _anio_mes(n.fecha_captura)
    flags = list(n.calidad_flags)
    if declarado.copia_de:
        flags.append(FLAG_SOSPECHA_COPIA)

    registro = {
        "tienda": declarado.tienda,
        "anio_mes": declarado.anio_mes,
        "sku": n.sku,
        "precio_actual": n.precio_actual,
        "precio_oferta": n.precio_oferta,
        "fecha_captura": _utc(n.fecha_captura),
        "sku_raw": n.sku_raw,
        "precio_actual_raw": n.precio_actual_raw,
        "precio_oferta_raw": n.precio_oferta_raw,
        "fecha_captura_raw": n.fecha_captura_raw,
        "tienda_raw": esquema.valor(fila, "tienda"),
        "calidad_flags": flags,
        "precio_parse_ok": n.precio_parse_ok,
        "fecha_parse_ok": n.fecha_parse_ok,
        "sku_es_centinela": n.sku_es_centinela,
        "fila_vacia": n.fila_vacia,
        # Sin fecha no hay con qué comparar: no se afirma un desfase.
        "desfase_mes": anio_mes_dato is not None and anio_mes_dato != declarado.anio_mes,
        "anio_mes_dato": anio_mes_dato,
        "_archivo_origen": declarado.ruta,
        "_md5_origen": md5,
        "_variante_schema": esquema.variante,
        "_fila_num": numero,
        "_ingestado_en": ingestado_en,
    }
    registro.update({columna: esquema.valor(fila, columna) for columna in COLUMNAS_TEXTO})
    return registro


def _anio_mes(fecha: datetime | None) -> str | None:
    """`2026-03-06 02:32` -> `2026-03`; sin fecha, None."""
    return None if fecha is None else f"{fecha.year:04d}-{fecha.month:02d}"


def _utc(fecha: datetime | None) -> datetime | None:
    """Etiqueta la hora de pared como UTC, sin desplazarla."""
    return None if fecha is None else fecha.replace(tzinfo=UTC)
