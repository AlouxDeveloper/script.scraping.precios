"""Construcción de los clientes de Google Cloud, a partir de `gcp.yml`.

Ni un factory de aquí abre una conexión ni resuelve credenciales por sí mismo:
solo instancian el cliente con el `project_id` y la `location` de la config, y
delegan la autenticación en las Application Default Credentials (`gcloud auth
application-default login`). Aíslan esa decisión para que `manifest`, `raw` y
`bronce` no repitan el mismo `Client(project=...)` con criterios distintos.
"""

from google.cloud import bigquery, storage
from google.cloud.storage.retry import DEFAULT_RETRY

from precios_load.config import ConfigGCP

# Backoff exponencial de la librería (cubre 429/5xx y cortes de conexión), con
# un techo de tiempo por objeto para que un blip no cuelgue la corrida. Lo
# comparten las subidas de raw y de bronce.
REINTENTO_SUBIDA = DEFAULT_RETRY.with_timeout(300.0)


def cliente_bq(config: ConfigGCP) -> bigquery.Client:
    """Cliente de BigQuery fijado al proyecto y la ubicación de la config.

    La `location` explícita evita que un job se cree en `US` por defecto cuando
    el dataset vive en otra multi-región.
    """
    return bigquery.Client(project=config.project_id, location=config.location)


def cliente_gcs(config: ConfigGCP) -> storage.Client:
    """Cliente de Cloud Storage fijado al proyecto de la config."""
    return storage.Client(project=config.project_id)
