"""El manifest de ingesta: el estado de idempotencia, en BigQuery.

Qué archivo se subió, con qué MD5, a dónde y con qué resultado. Vive en una
tabla de control (`precios_raw._ingesta_manifest`) y no en un archivo local:
así sobrevive a cambiar de máquina, lo puede consultar cualquiera del equipo y
queda auditable.

Dos reglas que sostienen la idempotencia:

1. **Append-only.** Cada ingesta de un archivo inserta una fila nueva; el
   estado actual de una ruta es su fila de mayor `version`. Una recarga (MD5
   distinto) no pisa la fila anterior, incrementa `version`. BigQuery no tiene
   clave primaria ni `UPDATE` barato, y el historial completo es justo lo que
   hace la tabla auditable.
2. **Se escribe al final.** `registrar` se llama solo cuando raw y bronce ya
   están confirmados. Una corrida que se interrumpe antes no deja fila, así que
   al reanudar el archivo se vuelve a intentar entero y el manifest nunca
   afirma un estado que no ocurrió.
"""

import base64
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage

from precios_load.config import ConfigGCP
from precios_load.descubrimiento import ArchivoFuente

# Nombre por defecto de la tabla. Los tests lo sustituyen por uno desechable, y
# `_tabla()` lo resuelve en cada llamada para que ese reemplazo surta efecto.
TABLA_MANIFEST = "_ingesta_manifest"


def _tabla(nombre: str | None) -> str:
    """El nombre de tabla efectivo: el que se pasó, o el por defecto vigente."""
    return nombre if nombre is not None else TABLA_MANIFEST

# Estado del archivo tras la ingesta.
ESTADO_OK = "OK"
ESTADO_VACIO = "VACIO"
ESTADO_ERROR = "ERROR"

# Qué hacer con un archivo al compararlo contra el manifest.
SUBIR = "subir"
SALTAR = "saltar"

# El esquema de la tabla de control. Sin partición ni cluster: son ~150 filas
# por corrida, el coste de escaneo es irrelevante y particionarla solo añade
# fricción.
ESQUEMA_MANIFEST = (
    # Clave lógica y partición del lake.
    bigquery.SchemaField("ruta_origen", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("tienda", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("anio_mes", "STRING", mode="REQUIRED"),
    # Base de la comparación de idempotencia.
    bigquery.SchemaField("md5_origen", "STRING", mode="REQUIRED"),
    # Reconciliación de conteos entre local, raw y bronce. INTEGER es el nombre
    # heredado de INT64 en la API; es el que BigQuery devuelve al releer.
    bigquery.SchemaField("bytes_origen", "INTEGER"),
    bigquery.SchemaField("filas_origen", "INTEGER"),
    bigquery.SchemaField("filas_bronce", "INTEGER"),
    # Dónde quedó el dato.
    bigquery.SchemaField("uri_raw", "STRING"),
    bigquery.SchemaField("uri_bronce", "STRING"),
    # Linaje y calidad a nivel archivo.
    bigquery.SchemaField("variante_schema", "STRING"),
    bigquery.SchemaField("estado", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("flags", "STRING", mode="REPEATED"),
    # Cuándo y qué número de carga.
    bigquery.SchemaField("ingestado_en", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("version", "INTEGER", mode="REQUIRED"),
)


@dataclass(frozen=True)
class FilaManifest:
    """Una fila del manifest: el resultado de ingerir un archivo una vez.

    Los campos opcionales quedan en `None` mientras no apliquen: un archivo
    `VACIO` no tiene `uri_bronce` ni `filas_bronce`, y `ingestado_en` lo pone
    `registrar` si el llamador no lo fijó.
    """

    ruta_origen: str
    tienda: str
    anio_mes: str
    md5_origen: str
    estado: str
    version: int
    bytes_origen: int | None = None
    filas_origen: int | None = None
    filas_bronce: int | None = None
    uri_raw: str | None = None
    uri_bronce: str | None = None
    variante_schema: str | None = None
    flags: tuple[str, ...] = ()
    ingestado_en: datetime | None = None


@dataclass(frozen=True)
class Decision:
    """Qué hacer con un archivo tras compararlo contra el manifest."""

    accion: str
    version: int
    motivo: str = ""
    fila_previa: FilaManifest | None = None

    @property
    def sube(self) -> bool:
        return self.accion == SUBIR


def decidir(
    fuente: ArchivoFuente,
    estado: dict[str, FilaManifest],
    cliente_gcs: storage.Client | None = None,
    config: ConfigGCP | None = None,
) -> Decision:
    """Compara un archivo contra el estado del manifest.

    - Sin registro previo: se sube en `version` 1, salvo que la red de seguridad
      lo desmienta (ver abajo).
    - MD5 idéntico al registrado: se salta, sin tocar la red de datos.
    - MD5 distinto: recarga del mes en curso, se sube con `version` incrementada.

    Red de seguridad: si no hay registro previo pero el objeto ya está en la
    capa raw y su `md5_hash` coincide con el del archivo local, se salta la
    subida igual. Cubre el caso de un manifest que se perdió o se recreó vacío
    con datos ya en GCS. Solo se consulta cuando se pasan `cliente_gcs` y
    `config`; con MD5 registrado no se llega hasta aquí.
    """
    previa = estado.get(fuente.ruta)

    if previa is None:
        if cliente_gcs is not None and config is not None:
            return _decidir_contra_gcs(fuente, cliente_gcs, config)
        return Decision(accion=SUBIR, version=1)

    if previa.md5_origen == fuente.md5:
        return Decision(
            accion=SALTAR,
            version=previa.version,
            motivo="MD5 sin cambios",
            fila_previa=previa,
        )

    return Decision(
        accion=SUBIR,
        version=previa.version + 1,
        motivo="MD5 distinto: recarga",
        fila_previa=previa,
    )


def _decidir_contra_gcs(
    fuente: ArchivoFuente, cliente_gcs: storage.Client, config: ConfigGCP
) -> Decision:
    """Red de seguridad: compara el archivo local contra el objeto en raw."""
    objeto = config.uri_raw(
        fuente.tienda, fuente.anio_mes, fuente.nombre
    ).removeprefix(f"gs://{config.bucket_raw}/")
    blob = cliente_gcs.bucket(config.bucket_raw).get_blob(objeto)

    if blob is not None and _md5_hex(blob.md5_hash) == fuente.md5:
        return Decision(accion=SALTAR, version=1, motivo="ya en GCS, MD5 coincide")

    return Decision(accion=SUBIR, version=1)


def _md5_hex(md5_hash: str | None) -> str | None:
    """`blob.md5_hash` viene en base64; el MD5 local es hex. Iguala los formatos."""
    return None if md5_hash is None else base64.b64decode(md5_hash).hex()


def crear_tabla(
    cliente: bigquery.Client, config: ConfigGCP, tabla: str | None = None
) -> bool:
    """Crea la tabla del manifest si no existe. Devuelve True solo si la creó.

    Idempotente: si ya existe se deja intacta, nunca se redefine su esquema.
    """
    ref = config.tabla(_tabla(tabla))
    try:
        cliente.get_table(ref)
        return False
    except NotFound:
        # exists_ok tolera la carrera de dos corridas creando la tabla a la vez.
        cliente.create_table(
            bigquery.Table(ref, schema=list(ESQUEMA_MANIFEST)), exists_ok=True
        )
        return True


def leer_estado(
    cliente: bigquery.Client, config: ConfigGCP, tabla: str | None = None
) -> dict[str, FilaManifest]:
    """El estado actual del manifest: la fila de mayor `version` por `ruta_origen`.

    Si la tabla aún no existe, la crea y devuelve `{}`: la primera ingesta parte
    de un manifest vacío, no de un error.
    """
    tabla = _tabla(tabla)
    crear_tabla(cliente, config, tabla)

    consulta = f"""
        SELECT * EXCEPT(_rn) FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY ruta_origen ORDER BY version DESC
            ) AS _rn
            FROM `{config.tabla(tabla)}`
        )
        WHERE _rn = 1
    """
    return {
        fila.ruta_origen: _de_row(fila) for fila in cliente.query(consulta).result()
    }


def registrar(
    cliente: bigquery.Client,
    config: ConfigGCP,
    filas: list[FilaManifest],
    tabla: str | None = None,
) -> None:
    """Añade filas al manifest. Append-only: nunca actualiza ni borra.

    Se llama **al final** de la ingesta, con raw y bronce ya confirmados. Usa un
    load job (no streaming) para que el `leer_estado` de la siguiente corrida
    vea las filas sin esperar al buffer de streaming.
    """
    if not filas:
        return

    tabla = _tabla(tabla)
    crear_tabla(cliente, config, tabla)
    ahora = datetime.now(UTC)
    registros = [
        _a_json(f if f.ingestado_en else replace(f, ingestado_en=ahora)) for f in filas
    ]

    job_config = bigquery.LoadJobConfig(
        schema=list(ESQUEMA_MANIFEST),
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    cliente.load_table_from_json(
        registros, config.tabla(tabla), job_config=job_config
    ).result()


def resumen(
    cliente: bigquery.Client, config: ConfigGCP, tabla: str | None = None
) -> list[str]:
    """El manifest como lista de líneas, para el comando `estado`.

    Cuenta sobre el estado actual (una fila por `ruta_origen`): archivos por
    estado, cuántos se recargaron alguna vez, y el desglose por tienda y por
    mes con la suma de filas de origen.
    """
    tabla = _tabla(tabla)
    estado = leer_estado(cliente, config, tabla)
    filas = list(estado.values())

    por_estado = _conteo(f.estado for f in filas)
    recargados = sum(1 for f in filas if f.version > 1)

    lineas = [
        f"Manifest de ingesta — {config.tabla(tabla)}",
        f"  archivos     {len(filas)}",
        "  estados      " + ("  ".join(f"{e} {n}" for e, n in por_estado) or "—"),
        f"  recargados   {recargados}",
        "",
        "POR TIENDA",
        *_tabla_agrupada(filas, lambda f: f.tienda),
        "",
        "POR MES",
        *_tabla_agrupada(filas, lambda f: f.anio_mes),
    ]
    return lineas


def _conteo(valores) -> list[tuple[str, int]]:
    """Cuenta ocurrencias y las devuelve ordenadas por clave."""
    cuenta: dict[str, int] = {}
    for valor in valores:
        cuenta[valor] = cuenta.get(valor, 0) + 1
    return sorted(cuenta.items())


def _tabla_agrupada(filas: list[FilaManifest], clave) -> list[str]:
    """Archivos y filas de origen agrupados por `clave`."""
    grupos: dict[str, tuple[int, int]] = {}
    for fila in filas:
        archivos, filas_origen = grupos.get(clave(fila), (0, 0))
        grupos[clave(fila)] = (archivos + 1, filas_origen + (fila.filas_origen or 0))
    return [
        f"  {g:<14} {archivos:>3} archivos  {filas_origen:>10,} filas"
        for g, (archivos, filas_origen) in sorted(grupos.items())
    ] or ["  (sin datos)"]


def _a_json(fila: FilaManifest) -> dict:
    """`FilaManifest` -> dict para el load job."""
    return {
        "ruta_origen": fila.ruta_origen,
        "tienda": fila.tienda,
        "anio_mes": fila.anio_mes,
        "md5_origen": fila.md5_origen,
        "bytes_origen": fila.bytes_origen,
        "filas_origen": fila.filas_origen,
        "filas_bronce": fila.filas_bronce,
        "uri_raw": fila.uri_raw,
        "uri_bronce": fila.uri_bronce,
        "variante_schema": fila.variante_schema,
        "estado": fila.estado,
        "flags": list(fila.flags),
        "ingestado_en": fila.ingestado_en.isoformat(),
        "version": fila.version,
    }


def _de_row(row: bigquery.table.Row) -> FilaManifest:
    """Fila de BigQuery -> `FilaManifest`."""
    return FilaManifest(
        ruta_origen=row["ruta_origen"],
        tienda=row["tienda"],
        anio_mes=row["anio_mes"],
        md5_origen=row["md5_origen"],
        estado=row["estado"],
        version=row["version"],
        bytes_origen=row["bytes_origen"],
        filas_origen=row["filas_origen"],
        filas_bronce=row["filas_bronce"],
        uri_raw=row["uri_raw"],
        uri_bronce=row["uri_bronce"],
        variante_schema=row["variante_schema"],
        flags=tuple(row["flags"]),
        ingestado_en=row["ingestado_en"],
    )
