"""El orquestador del comando `ingesta`: sube a raw, a bronce y registra el manifest.

Recorre las entradas del `plan` ya filtrado, consulta el manifest para decidir
qué archivo se salta y cuál se sube, sube los que toca a raw, ensambla su
Parquet a bronce y, **al final**, escribe una fila por archivo procesado.

La subida de cada archivo es independiente, así que corren en paralelo con un
`ThreadPoolExecutor`. El cuello de botella es el ancho de banda de subida, no el
CPU. Los resultados se recolectan en el orden de entrada, no en el de término.

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

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from google.cloud import bigquery, storage

from precios_load import bronce, manifest, raw
from precios_load.config import ConfigGCP
from precios_load.plan import EntradaPlan

# Cuántos archivos se suben a la vez. El límite es el ancho de banda de subida,
# no el CPU: 8 conexiones saturan un enlace normal sin apilar demasiada RAM
# (cada worker arma un DataFrame del archivo en memoria).
TRABAJADORES_SUBIDA = 8


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


@dataclass(frozen=True)
class _Salida:
    """El desenlace de un archivo, para recolectarlo en orden desde los workers.

    `categoria` es `"procesado"`, `"saltado"` o `"fallido"`. `fila` va en `None`
    cuando no debe entrar al manifest: un archivo saltado, o un fallo de
    reconciliación.
    """

    ruta: str
    categoria: str
    fila: manifest.FilaManifest | None
    mensaje: str | None = None


def ejecutar(
    cliente_bq: bigquery.Client,
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    entradas: list[EntradaPlan],
    base: str | None = None,
    tabla: str | None = None,
    trabajadores: int | None = None,
) -> ResultadoIngesta:
    """Sube a raw y a bronce las entradas que lo necesitan; escribe el manifest al final."""
    estado = manifest.leer_estado(cliente_bq, config, tabla)
    ingestado_en = datetime.now(UTC)

    n = trabajadores or TRABAJADORES_SUBIDA
    with ThreadPoolExecutor(max_workers=max(1, min(n, len(entradas) or 1))) as executor:
        salidas = list(
            executor.map(
                lambda entrada: _procesar_una(
                    entrada, estado, cliente_gcs, config, base, ingestado_en
                ),
                entradas,
            )
        )

    filas: list[manifest.FilaManifest] = []
    procesados: list[str] = []
    saltados: list[str] = []
    fallidos: list[tuple[str, str]] = []

    for salida in salidas:
        if salida.categoria == "saltado":
            saltados.append(salida.ruta)
        elif salida.categoria == "procesado":
            procesados.append(salida.ruta)
            filas.append(salida.fila)
        else:
            fallidos.append((salida.ruta, salida.mensaje))
            if salida.fila is not None:
                filas.append(salida.fila)

    manifest.registrar(cliente_bq, config, filas, tabla)
    return ResultadoIngesta(tuple(procesados), tuple(saltados), tuple(fallidos))


def _procesar_una(
    entrada: EntradaPlan,
    estado: dict[str, manifest.FilaManifest],
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    base: str | None,
    ingestado_en: datetime,
) -> _Salida:
    """Sube un archivo a raw y a bronce. Nunca lanza: cada desenlace vuelve como `_Salida`."""
    fuente = entrada.fuente
    decision = manifest.decidir(fuente, estado, cliente_gcs, config)

    if not decision.sube:
        return _Salida(fuente.ruta, "saltado", None)

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
    except bronce.ErrorReconciliacion as e:
        # Pérdida silenciosa de filas: no se registra nada. Que la próxima
        # corrida lo reintente desde cero, una vez arreglado el parser.
        return _Salida(fuente.ruta, "fallido", None, str(e))
    except Exception as e:  # noqa: BLE001 - un archivo no puede tumbar la corrida
        fila = _fila(entrada, decision, manifest.ESTADO_ERROR, uri_raw, None, None)
        return _Salida(fuente.ruta, "fallido", fila, str(e))

    fila = _fila(entrada, decision, estado_fila, uri_raw, uri_bronce, filas_bronce)
    return _Salida(fuente.ruta, "procesado", fila)


def _fila(
    entrada: EntradaPlan,
    decision: manifest.Decision,
    estado_fila: str,
    uri_raw: str | None,
    uri_bronce: str | None,
    filas_bronce: int | None,
) -> manifest.FilaManifest:
    """Arma la fila del manifest para un archivo ya subido (o fallido tras raw)."""
    fuente = entrada.fuente
    return manifest.FilaManifest(
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
