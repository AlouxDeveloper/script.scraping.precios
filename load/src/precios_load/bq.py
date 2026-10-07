"""Setup de BigQuery: las external tables BigLake sobre la capa bronce.

Es la frontera de `load/`: `bq-setup` corre DDLs `CREATE OR REPLACE EXTERNAL
TABLE`, idempotentes por construcción, que dejan el histórico (`precios_ext`),
el catálogo NDF (`ndf_ext`) y el puente aportador (`puente_aportador_ext`)
consultables. Un Parquet nuevo en GCS es visible al instante, sin job de carga.

Bronce vive en GCS; `precios_bronce` solo lo mira. La limpieza y las capas
silver/gold son trabajo de dbt sobre estas tablas, no de este módulo.
"""

import pyarrow as pa
from google.cloud import bigquery

from precios_load.config import ConfigGCP
from precios_load.precios_v2 import ESQUEMA_P1

# Nombres por defecto. Los tests los sustituyen por tablas desechables que
# apuntan al mismo prefijo de GCS.
TABLA_BRONCE_EXT = "precios_ext"
TABLA_NDF_EXT = "ndf_ext"
TABLA_PUENTE_APORTADOR_EXT = "puente_aportador_ext"

# Los catálogos viven en subdirectorios propios del prefijo de catálogos. El
# glob es explícito (`*.parquet`) porque ahí no hay particiones hive que
# delimiten el conjunto, a diferencia de precios.
GLOB_NDF = "ndf/*.parquet"
GLOB_PUENTE_APORTADOR = "puente_aportador/*.parquet"


def crear_external_bronce(
    cliente: bigquery.Client, config: ConfigGCP, tabla: str | None = None
) -> str:
    """Crea o reemplaza la external table sobre `gs://<bucket_bronce>/<prefijo>`.

    Devuelve la referencia completa de la tabla. `CREATE OR REPLACE` la hace
    idempotente.

    Dos detalles de sintaxis que BigQuery no perdona:

    - `WITH PARTITION COLUMNS` va **antes** de `WITH CONNECTION`. Al revés,
      responde `Syntax error: Expected keyword OPTIONS but got keyword WITH`.
    - `hive_partition_uri_prefix` **exige** `WITH PARTITION COLUMNS`. El modo
      CUSTOM (tipos declarados, no inferidos) se logra con la lista de columnas
      tipadas; así `anio_mes` queda STRING y no se infiere como fecha o entero.

    `tienda` y `anio_mes` están también dentro del Parquet: como el nombre y el
    tipo coinciden, BigQuery fusiona la columna del archivo con la de partición
    y el valor sale del path.

    El esquema va explícito (el de P1, que incluye las 26 columnas del
    histórico). Inferido, BigQuery toma el del archivo alfabéticamente último,
    que es del histórico, y las columnas de precios_v2 desaparecerían. Con el
    esquema explícito, un Parquet viejo lee NULL en las columnas que no trae.
    """
    referencia = config.tabla_bronce(tabla or TABLA_BRONCE_EXT)
    prefijo = config.prefijo_bronce()
    columnas = ",\n          ".join(
        f"`{campo.name}` {tipo_sql(campo.type)}" for campo in ESQUEMA_P1
        if campo.name not in ("tienda", "anio_mes"))

    ddl = f"""
        CREATE OR REPLACE EXTERNAL TABLE `{referencia}` (
          {columnas}
        )
        WITH PARTITION COLUMNS (
          tienda STRING,
          anio_mes STRING
        )
        WITH CONNECTION `{config.conexion()}`
        OPTIONS (
          format = 'PARQUET',
          uris = ['{prefijo}/*'],
          hive_partition_uri_prefix = '{prefijo}',
          require_hive_partition_filter = false
        )
    """
    cliente.query(ddl).result()
    return referencia


def tipo_sql(tipo: pa.DataType) -> str:
    """Tipo de BigQuery con el que una external table lee ese tipo de Parquet.

    Sin `enable_list_inference`, una lista llega como
    `STRUCT<list ARRAY<STRUCT<element>>>` (así lee staging `calidad_flags`) y
    un mapa como `STRUCT<key_value ARRAY<STRUCT<key, value>>>`. El decimal de
    bronce (38, 9) es NUMERIC.
    """
    if pa.types.is_map(tipo):
        return (f"STRUCT<key_value ARRAY<STRUCT<key {tipo_sql(tipo.key_type)}, "
                f"value {tipo_sql(tipo.item_type)}>>>")
    if pa.types.is_list(tipo):
        return f"STRUCT<list ARRAY<STRUCT<element {tipo_sql(tipo.value_type)}>>>"
    if pa.types.is_decimal(tipo):
        return "NUMERIC"
    if pa.types.is_timestamp(tipo):
        return "TIMESTAMP"
    return {pa.string(): "STRING", pa.bool_(): "BOOL",
            pa.int64(): "INT64"}[tipo]


def crear_external_ndf(
    cliente: bigquery.Client, config: ConfigGCP, tabla: str | None = None
) -> str:
    """Crea o reemplaza la external table sobre el Parquet del catálogo NDF.

    Sin hive partitioning: un catálogo es un solo archivo de reemplazo, no una
    serie de particiones, así que no lleva `WITH PARTITION COLUMNS` ni
    `hive_partition_uri_prefix`. El esquema lo infiere BigQuery del Parquet, que
    ya viene todo STRING desde `catalogos.py`.

    Sus `uris` (`<prefijo_catalogos>/ndf/*.parquet`) no solapan con las de
    `precios_ext` (`<prefijo_precios>/*`): son prefijos hermanos dentro del
    mismo bucket.
    """
    referencia = config.tabla_bronce(tabla or TABLA_NDF_EXT)
    uris = f"{config.prefijo_bronce_catalogos()}/{GLOB_NDF}"

    ddl = f"""
        CREATE OR REPLACE EXTERNAL TABLE `{referencia}`
        WITH CONNECTION `{config.conexion()}`
        OPTIONS (
          format = 'PARQUET',
          uris = ['{uris}']
        )
    """
    cliente.query(ddl).result()
    return referencia


def crear_external_puente_aportador(
    cliente: bigquery.Client, config: ConfigGCP, tabla: str | None = None
) -> str:
    """Crea o reemplaza la external table sobre el Parquet del puente aportador.

    Mismo criterio que `crear_external_ndf`: sin hive partitioning, un
    catálogo es un solo archivo de reemplazo. Sus `uris`
    (`<prefijo_catalogos>/puente_aportador/*.parquet`) son un prefijo hermano
    de `ndf/` y de `precios_ext`, no se solapan.
    """
    referencia = config.tabla_bronce(tabla or TABLA_PUENTE_APORTADOR_EXT)
    uris = f"{config.prefijo_bronce_catalogos()}/{GLOB_PUENTE_APORTADOR}"

    ddl = f"""
        CREATE OR REPLACE EXTERNAL TABLE `{referencia}`
        WITH CONNECTION `{config.conexion()}`
        OPTIONS (
          format = 'PARQUET',
          uris = ['{uris}']
        )
    """
    cliente.query(ddl).result()
    return referencia
