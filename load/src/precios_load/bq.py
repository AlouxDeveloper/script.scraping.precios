"""Setup de BigQuery: la external table BigLake sobre la capa bronce.

`bq-setup` corre un DDL `CREATE OR REPLACE`. La external table con hive
partitioning es lo que hace que un Parquet nuevo en una partición de GCS sea
visible en BigQuery al instante, sin job de carga ni orquestación.

Bronce vive en GCS; este dataset (`precios_bronce`) solo lo mira. No hay tabla
nativa aquí: materializar es cosa de silver.
"""

from google.cloud import bigquery

from precios_load.config import ConfigGCP

# Nombre por defecto de la external table. Los tests lo sustituyen por uno
# desechable que apunta al mismo prefijo de GCS.
TABLA_BRONCE_EXT = "precios_ext"


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
