"""Setup de BigQuery: las external tables BigLake sobre la capa bronce.

Es la frontera de `load/`: `bq-setup` corre DDLs `CREATE OR REPLACE EXTERNAL
TABLE`, idempotentes por construcción, que dejan el histórico (`precios_ext`) y
el catálogo NDF (`ndf_ext`) consultables. Un Parquet nuevo en GCS es visible al
instante, sin job de carga.

Bronce vive en GCS; `precios_bronce` solo lo mira. La limpieza y las capas
silver/gold son trabajo de dbt sobre estas tablas, no de este módulo.
"""

from google.cloud import bigquery

from precios_load.config import ConfigGCP

# Nombres por defecto. Los tests los sustituyen por tablas desechables que
# apuntan al mismo prefijo de GCS.
TABLA_BRONCE_EXT = "precios_ext"
TABLA_NDF_EXT = "ndf_ext"

# El catálogo NDF vive en un subdirectorio propio del prefijo de catálogos. El
# glob es explícito (`*.parquet`) porque aquí no hay particiones hive que
# delimiten el conjunto, a diferencia de precios.
GLOB_NDF = "ndf/*.parquet"


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
    """
    referencia = config.tabla_bronce(tabla or TABLA_BRONCE_EXT)
    prefijo = config.prefijo_bronce()

    ddl = f"""
        CREATE OR REPLACE EXTERNAL TABLE `{referencia}`
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
