"""El orquestador del comando `ingesta`: sube a raw y registra el manifest.

Recorre las entradas del `plan` ya filtrado, consulta el manifest para decidir
qué archivo se salta y cuál se sube, sube los que toca a la capa raw y, **al
final**, escribe una fila por archivo procesado.

Reglas heredadas de ALD-17:

- El manifest se escribe una sola vez, al terminar. Una corrida interrumpida no
  deja filas y la siguiente la reanuda.
- Un archivo que falla no frena la corrida: deja fila `ERROR` y se reintenta en
  la siguiente pasada.

Las fases de bronce (ALD-20) y la reconciliación (ALD-21) se enganchan aquí; por
eso `uri_bronce` y `filas_bronce` de la fila van en `None` en esta etapa.
"""

from dataclasses import dataclass

from google.cloud import bigquery, storage

from precios_load import manifest, raw
from precios_load.config import ConfigGCP
from precios_load.plan import EntradaPlan


@dataclass(frozen=True)
class ResultadoIngesta:
    """Qué pasó con cada archivo de la corrida."""

    subidos: tuple[str, ...]
    saltados: tuple[str, ...]
    errores: tuple[tuple[str, str], ...]  # (ruta, mensaje)

    @property
    def filas_registradas(self) -> int:
        """Filas que se escribieron en el manifest: subidos + errores."""
        return len(self.subidos) + len(self.errores)


def ejecutar(
    cliente_bq: bigquery.Client,
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    entradas: list[EntradaPlan],
    base: str | None = None,
    tabla: str | None = None,
) -> ResultadoIngesta:
    """Sube a raw las entradas que lo necesitan y escribe el manifest al final."""
    estado = manifest.leer_estado(cliente_bq, config, tabla)

    filas: list[manifest.FilaManifest] = []
    subidos: list[str] = []
    saltados: list[str] = []
    errores: list[tuple[str, str]] = []

    for entrada in entradas:
        fuente = entrada.fuente
        decision = manifest.decidir(fuente, estado, cliente_gcs, config)

        if not decision.sube:
            saltados.append(fuente.ruta)
            continue

        try:
            uri_raw = raw.subir(cliente_gcs, config, fuente, base=base)
            estado_fila = (
                manifest.ESTADO_VACIO if fuente.vacio else manifest.ESTADO_OK
            )
            subidos.append(fuente.ruta)
        except Exception as e:  # noqa: BLE001 - un archivo no puede tumbar la corrida
            uri_raw = None
            estado_fila = manifest.ESTADO_ERROR
            errores.append((fuente.ruta, str(e)))

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
                variante_schema=fuente.variante,
                flags=tuple(entrada.flags),
            )
        )

    manifest.registrar(cliente_bq, config, filas, tabla)
    return ResultadoIngesta(tuple(subidos), tuple(saltados), tuple(errores))
