"""Setup de BigQuery: la external table de bronce y la tabla nativa de silver.

`bq-setup` corre DDLs `CREATE OR REPLACE`, idempotentes por construcción:

- `precios_bronce.precios_ext` — external table con hive partitioning. Hace que
  un Parquet nuevo en GCS sea visible al instante, sin job de carga. Bronce vive
  en GCS; este dataset solo lo mira.
- `precios_silver.precios` — copia nativa de bronce (12 columnas, todas las
  filas), particionada y clusterizada. Sin transformar: limpieza y dimensiones
  son cosa de dbt.
"""

from google.cloud import bigquery

from precios_load.config import ConfigGCP

# Nombres por defecto. Los tests los sustituyen por tablas desechables que
# apuntan a los mismos datos.
TABLA_BRONCE_EXT = "precios_ext"
TABLA_SILVER = "precios"


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


# Las 12 columnas de bronce que se materializan en silver, verbatim. Sin
# derivar, sin renombrar: la limpieza y las dimensiones son cosa de dbt.
COLUMNAS_SILVER = (
    "tienda",           # slug estable — clave de join al futuro dim_tienda
    "tienda_raw",       # literal del scraper (número o nombre) — trazabilidad
    "sku",
    "producto",
    "url_producto",
    "url_imagen",
    "precio_actual",
    "precio_oferta",
    "fecha_captura",
    "anio_mes",
    "_archivo_origen",
    "_ingestado_en",
)


def crear_tabla_silver(
    cliente: bigquery.Client, config: ConfigGCP, tabla: str | None = None
) -> str:
    """Materializa `precios_silver.precios` como copia nativa de bronce.

    Devuelve la referencia completa. `CREATE OR REPLACE ... AS SELECT` la hace
    idempotente.

    No transforma nada: proyecta 12 de las 26 columnas de `precios_ext`,
    verbatim, todas las filas. Lo único que se decide aquí es el layout físico
    (`PARTITION BY` mes de `fecha_captura`, `CLUSTER BY tienda, sku`), que acomoda
    los datos pero no los cambia. La limpieza, la deduplicación y el catálogo de
    tiendas son trabajo de dbt, aguas abajo.
    """
    referencia = config.tabla_silver(tabla or TABLA_SILVER)
    fuente = config.tabla_bronce(TABLA_BRONCE_EXT)
    columnas = ",\n          ".join(COLUMNAS_SILVER)

    ddl = f"""
        CREATE OR REPLACE TABLE `{referencia}`
        PARTITION BY DATE_TRUNC(fecha_captura, MONTH)
        CLUSTER BY tienda, sku
        AS
        SELECT
          {columnas}
        FROM `{fuente}`
    """
    cliente.query(ddl).result()
    return referencia
