"""La capa raw: el CSV original, subido a Cloud Storage byte por byte.

Raw es la fuente inmutable del lake. Aquí no se corrige, no se normaliza y no se
descarta nada: si mañana un parser de bronce tiene un bug, bronce se regenera
desde raw sin volver a scrapear. El objeto conserva el nombre original del
archivo, incluidos los raros (`aurrera1`, `fahorro_a`); la partición (`tienda=`,
`anio_mes=`) sale de la carpeta de origen, no del contenido.
"""

import base64
import os

from google.cloud import storage
from google.cloud.storage.retry import DEFAULT_RETRY

from precios_load.config import ConfigGCP
from precios_load.descubrimiento import ArchivoFuente

# El backoff exponencial de la librería (cubre 429/5xx y cortes de conexión),
# con un techo de tiempo por archivo para que un blip no cuelgue la corrida.
_REINTENTO = DEFAULT_RETRY.with_timeout(300.0)


class ErrorSubidaRaw(Exception):
    """El objeto subido a GCS no es byte-idéntico al archivo local."""


def subir(
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    fuente: ArchivoFuente,
    base: str | None = None,
) -> str:
    """Sube el CSV a la capa raw y verifica que quedó intacto. Devuelve la URI.

    `base` es la raíz local de los datos; por defecto, `salida/data`. La ruta del
    objeto sigue exactamente `precios/tienda=<slug>/anio_mes=<YYYY-MM>/<nombre>`.

    Lanza `ErrorSubidaRaw` si el `md5_hash` del objeto no coincide con el MD5 que
    `descubrimiento` calculó en disco.
    """
    base = base if base is not None else config.ruta_datos()
    ruta_local = os.path.join(base, fuente.ruta)
    uri = config.uri_raw(fuente.tienda, fuente.anio_mes, fuente.nombre)
    objeto = uri.removeprefix(f"gs://{config.bucket_raw}/")

    blob = cliente_gcs.bucket(config.bucket_raw).blob(objeto)
    blob.upload_from_filename(ruta_local, checksum="md5", retry=_REINTENTO)

    if blob.md5_hash is None:
        blob.reload()
    md5_remoto = base64.b64decode(blob.md5_hash).hex()
    if md5_remoto != fuente.md5:
        raise ErrorSubidaRaw(
            f"{fuente.ruta}: el objeto en GCS tiene md5 {md5_remoto}, "
            f"se esperaba {fuente.md5}"
        )
    return uri
