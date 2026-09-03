"""El orquestador del comando `ingesta`: sube a raw, a bronce y registra el manifest.

Recorre las entradas del `plan` ya filtrado, consulta el manifest para decidir
qué archivo se salta y cuál se sube, sube los que toca a raw, ensambla su
Parquet a bronce y, **al final**, escribe una fila por archivo procesado.

Reglas heredadas de ALD-17:

- El manifest se escribe una sola vez, al terminar. Una corrida interrumpida no
  deja filas y la siguiente la reanuda.
- Un archivo que falla no frena la corrida. Hay dos clases de fallo:
  - **Subida** (red, permisos): deja fila `ERROR`, se reintenta con `version+1`.
  - **Reconciliación** (el Parquet no cuadra en filas con el CSV): pérdida
    silenciosa de datos. No deja fila; se reporta con ambos conteos y hay que
    arreglar el parser antes de que la próxima corrida lo reintente.

Un archivo vacío (solo header) sube a raw como `VACIO` y no genera Parquet, así
que su fila lleva `uri_bronce` y `filas_bronce` en `None`. La reconciliación de
conteos vive en `bronce.escribir`; aquí solo se decide qué hacer con su fallo.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from google.cloud import bigquery, storage

from precios_load import bronce, manifest, raw
from precios_load.config import ConfigGCP
from precios_load.plan import EntradaPlan


@dataclass(frozen=True)
class ResultadoIngesta:
    """Qué pasó con cada archivo de la corrida.

    Un archivo `fallido` puede o no haber dejado fila en el manifest: un fallo de
    subida deja fila `ERROR` (se reintenta), un descuadre de reconciliación no
    deja nada (hay que arreglar el parser antes de reintentar).
    """

    procesados: tuple[str, ...]
    saltados: tuple[str, ...]
    fallidos: tuple[tuple[str, str], ...]  # (ruta, mensaje)


def ejecutar(
    cliente_bq: bigquery.Client,
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    entradas: list[EntradaPlan],
    base: str | None = None,
    tabla: str | None = None,
) -> ResultadoIngesta:
    """Sube a raw y a bronce las entradas que lo necesitan; escribe el manifest al final."""
    estado = manifest.leer_estado(cliente_bq, config, tabla)
    ingestado_en = datetime.now(UTC)

    filas: list[manifest.FilaManifest] = []
    procesados: list[str] = []
    saltados: list[str] = []
    fallidos: list[tuple[str, str]] = []

    for entrada in entradas:
        fuente = entrada.fuente
        decision = manifest.decidir(fuente, estado, cliente_gcs, config)

        if not decision.sube:
            saltados.append(fuente.ruta)
            continue

        uri_raw = None
        uri_bronce = None
        filas_bronce = None
        try:
            uri_raw = raw.subir(cliente_gcs, config, fuente, base=base)
            if fuente.vacio:
                # Un archivo sin filas no genera Parquet: queda VACIO en raw.
                estado_fila = manifest.ESTADO_VACIO
            else:
                uri_bronce, filas_bronce = bronce.escribir(
                    cliente_gcs, config, fuente, base=base, ingestado_en=ingestado_en
                )
                estado_fila = manifest.ESTADO_OK
            procesados.append(fuente.ruta)
        except bronce.ErrorReconciliacion as e:
            # Pérdida silenciosa de filas: no se registra nada. Que la próxima
            # corrida lo reintente desde cero, una vez arreglado el parser.
            fallidos.append((fuente.ruta, str(e)))
            continue
        except Exception as e:  # noqa: BLE001 - un archivo no puede tumbar la corrida
            estado_fila = manifest.ESTADO_ERROR
            fallidos.append((fuente.ruta, str(e)))

        filas.append(
            manifest.FilaManifest(
                ruta_origen=fuente.ruta,
                tienda=fuente.tienda,
                anio_mes=fuente.anio_mes,
                md5_origen=fuente.md5,
                estado=estado_fila,
                version=decision.version,
                bytes_origen=fuente.bytes,
                filas_origen=fuente.filas,
                uri_raw=uri_raw,
                uri_bronce=uri_bronce,
                filas_bronce=filas_bronce,
                variante_schema=fuente.variante,
                flags=tuple(entrada.flags),
            )
        )

    manifest.registrar(cliente_bq, config, filas, tabla)
    return ResultadoIngesta(tuple(procesados), tuple(saltados), tuple(fallidos))
