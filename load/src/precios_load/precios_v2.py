"""Ingesta de Scrapers 2.0 (`precios_v2`) hasta bronce, variante P1.

Implementa la sección 4.6 del PRD de Scrapers 2.0. A diferencia del
histórico, no hay inventario declarado: cada corrida se descubre por
convención bajo el origen (``./salida/data_v2`` o ``gs://.../precios_v2``)::

    tienda=<slug>/anio_mes=<AAAA-MM>/corrida=<corrida_id>/parte-NNNN.parquet
                                                         /_corrida.json

Reglas:

- Solo una corrida con ``estado = completa`` llega a bronce, y solo si el MD5
  de cada parte coincide con el de su ``_corrida.json``. Un descuadre deja la
  corrida fuera entera, sin fila en el manifest, igual que un
  ``ErrorReconciliacion`` del histórico.
- La idempotencia es la del histórico: una fila de manifest por parte, con su
  ruta relativa (prefijo ``precios_v2/``) y su MD5. Una parte ya ``OK`` con el
  mismo MD5 se salta.
- Todo ``_corrida.json`` (también parciales y abortadas) se carga en
  ``precios_ops._corridas_scraping`` para el monitoreo, una vez por contenido.
- Las partes no pasan por raw: el Parquet del scraper ya viene tipado y
  validado contra el contrato, y bronce P1 conserva todos sus campos.
"""

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import bigquery, storage
from pyarrow import fs

from precios_load import manifest
from precios_load.bronce import ESQUEMA_BRONCE
from precios_load.clientes import REINTENTO_SUBIDA
from precios_load.config import ConfigGCP

VARIANTE = "P1"
PREFIJO_RUTA = "precios_v2"
ZONA_MX = ZoneInfo("America/Mexico_City")

# Columnas del contrato v1 que el histórico no tiene. Van al final y nullable:
# en los Parquet viejos BigQuery las lee como NULL (verificado con una
# external table de esquema explícito, 2026-10-07).
COLUMNAS_NUEVAS = [
    pa.field("corrida_id", pa.string()),
    pa.field("contrato_version", pa.string()),
    pa.field("marca", pa.string()),
    pa.field("ean", pa.string()),
    pa.field("categoria_ruta", pa.list_(pa.string())),
    pa.field("moneda", pa.string()),
    pa.field("disponible", pa.bool_()),
    pa.field("zona_precio", pa.string()),
    pa.field("escalon", pa.string()),
    pa.field("url_fuente", pa.string()),
    pa.field("atributos_tienda", pa.map_(pa.string(), pa.string())),
    pa.field("capturado_en_utc", pa.timestamp("us", tz="UTC")),
]
ESQUEMA_P1 = pa.schema(list(ESQUEMA_BRONCE) + COLUMNAS_NUEVAS)

TABLA_CORRIDAS = "_corridas_scraping"
ESQUEMA_CORRIDAS = (
    bigquery.SchemaField("corrida_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("tienda", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("anio_mes", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("contrato_version", "STRING"),
    bigquery.SchemaField("estado", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("razon_cierre", "STRING"),
    bigquery.SchemaField("inicio", "TIMESTAMP"),
    bigquery.SchemaField("fin", "TIMESTAMP"),
    bigquery.SchemaField("partes", "RECORD", mode="REPEATED", fields=(
        bigquery.SchemaField("nombre", "STRING"),
        bigquery.SchemaField("filas", "INTEGER"),
        bigquery.SchemaField("md5", "STRING"),
    )),
    bigquery.SchemaField("filas_total", "INTEGER"),
    bigquery.SchemaField("unicos", "INTEGER"),
    bigquery.SchemaField("total_reportado", "INTEGER"),
    bigquery.SchemaField("cobertura", "FLOAT"),
    bigquery.SchemaField("peticiones", "INTEGER"),
    # Texto JSON: las claves (status HTTP) cambian por corrida.
    bigquery.SchemaField("respuestas_por_status", "STRING"),
    bigquery.SchemaField("bloqueos", "INTEGER"),
    bigquery.SchemaField("reintentos", "INTEGER"),
    bigquery.SchemaField("escalon", "STRING"),
    bigquery.SchemaField("entorno", "STRING"),
    bigquery.SchemaField("version_codigo", "STRING"),
    # Linaje de la carga: la fila vigente de una corrida es la de mayor
    # cargado_en (un parcial puede llegar antes que su versión final).
    bigquery.SchemaField("ruta_json", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("md5_json", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("cargado_en", "TIMESTAMP", mode="REQUIRED"),
)


@dataclass(frozen=True)
class Corrida:
    """Una corrida descubierta: su carpeta y su ``_corrida.json`` leído."""

    carpeta: str  # relativa al origen: tienda=/anio_mes=/corrida=
    tienda: str
    anio_mes: str
    datos: dict
    md5_json: str

    @property
    def completa(self) -> bool:
        return self.datos.get("estado") == "completa"


@dataclass(frozen=True)
class ParteV2:
    """Una parte Parquet. Tiene los atributos que ``manifest.decidir`` lee."""

    ruta: str  # clave del manifest: precios_v2/<carpeta>/<nombre>
    tienda: str
    anio_mes: str
    md5: str
    filas: int
    contenido: bytes

    @property
    def vacio(self) -> bool:
        return self.filas == 0

    @property
    def nombre(self) -> str:
        return self.ruta.rsplit("/", 1)[1]


@dataclass(frozen=True)
class ResultadoV2:
    """Qué pasó en una ingesta de precios_v2."""

    procesadas: tuple[str, ...]
    saltadas: tuple[str, ...]
    fallidas: tuple[tuple[str, str], ...]  # (carpeta o ruta, mensaje)
    corridas_omitidas: tuple[str, ...]  # no completas: no van a bronce
    jsons_cargados: int


class ErrorPartes(Exception):
    """Las partes en disco no cuadran con su ``_corrida.json``."""


def abrir_origen(origen: str) -> tuple[fs.FileSystem, str]:
    """Filesystem y raíz para una carpeta local o una URI gs://."""
    if "://" not in origen:
        origen = Path(origen).resolve().as_posix()
    return fs.FileSystem.from_uri(origen)


def descubrir(origen: str) -> tuple[fs.FileSystem, str, list[Corrida]]:
    """Todas las corridas con ``_corrida.json`` bajo el origen."""
    sistema, raiz = abrir_origen(origen)
    info = sistema.get_file_info(fs.FileSelector(raiz, allow_not_found=True,
                                                 recursive=True))
    corridas = []
    for archivo in sorted(i.path for i in info if i.base_name == "_corrida.json"):
        carpeta = archivo.removeprefix(raiz).strip("/").rsplit("/", 1)[0]
        tienda, anio_mes, _ = (p.split("=", 1)[1] for p in carpeta.split("/"))
        with sistema.open_input_stream(archivo) as f:
            crudo = f.read()
        corridas.append(Corrida(carpeta, tienda, anio_mes, json.loads(crudo),
                                hashlib.md5(crudo).hexdigest()))
    return sistema, raiz, corridas


def leer_partes(sistema: fs.FileSystem, raiz: str,
                corrida: Corrida) -> list[ParteV2]:
    """Lee las partes que declara el JSON y verifica su MD5."""
    partes = []
    for declarada in corrida.datos["partes"]:
        ruta = f"{raiz}/{corrida.carpeta}/{declarada['nombre']}"
        with sistema.open_input_stream(ruta) as f:
            contenido = f.read()
        md5 = hashlib.md5(contenido).hexdigest()
        if md5 != declarada["md5"]:
            raise ErrorPartes(
                f"{corrida.carpeta}/{declarada['nombre']}: MD5 {md5} no "
                f"coincide con el de _corrida.json ({declarada['md5']})")
        partes.append(ParteV2(
            ruta=f"{PREFIJO_RUTA}/{corrida.carpeta}/{declarada['nombre']}",
            tienda=corrida.tienda, anio_mes=corrida.anio_mes, md5=md5,
            filas=declarada["filas"], contenido=contenido))
    return partes


def a_p1(parte: ParteV2, ingestado_en: datetime) -> pa.Table:
    """Mapea una parte del contrato v1 a las columnas de bronce P1."""
    filas = pq.read_table(io.BytesIO(parte.contenido)).to_pylist()
    registros = [_registro(fila, parte, numero, ingestado_en)
                 for numero, fila in enumerate(filas, start=1)]
    return pa.Table.from_pylist(registros, schema=ESQUEMA_P1)


def _registro(fila: dict, parte: ParteV2, numero: int,
              ingestado_en: datetime) -> dict:
    """Una fila del contrato v1 convertida a P1."""
    capturado = fila["capturado_en"]
    # Mismo criterio que el histórico: fecha_captura es la hora de pared de
    # la Ciudad de México etiquetada como UTC, para que date(fecha_captura)
    # en staging siga siendo el día local. El UTC real va aparte.
    local = capturado.astimezone(ZONA_MX)
    anio_mes_dato = f"{local.year:04d}-{local.month:02d}"
    lista, oferta = fila["precio_lista"], fila["precio_oferta"]
    return {
        "tienda": parte.tienda,
        "anio_mes": parte.anio_mes,
        "sku": fila["sku_tienda"],
        "url_producto": fila["url_producto"],
        "producto": fila["producto"],
        "url_imagen": fila["url_imagen"],
        "precio_actual": lista,
        "precio_oferta": oferta,
        "fecha_captura": local.replace(tzinfo=UTC),
        "sku_raw": fila["sku_tienda"],
        "precio_actual_raw": None if lista is None else str(lista),
        "precio_oferta_raw": None if oferta is None else str(oferta),
        "fecha_captura_raw": capturado.isoformat(),
        "tienda_raw": fila["tienda"],
        # El contrato ya validó en el scraper lo que estas banderas miden en
        # el histórico, así que aquí solo pueden ser verdaderas o vacías.
        "calidad_flags": [],
        "precio_parse_ok": lista is not None or oferta is not None,
        "fecha_parse_ok": True,
        "sku_es_centinela": False,
        "fila_vacia": False,
        "desfase_mes": anio_mes_dato != parte.anio_mes,
        "anio_mes_dato": anio_mes_dato,
        "_archivo_origen": parte.ruta,
        "_md5_origen": parte.md5,
        "_variante_schema": VARIANTE,
        "_fila_num": numero,
        "_ingestado_en": ingestado_en,
        **{campo.name: fila.get(campo.name) for campo in COLUMNAS_NUEVAS
           if campo.name != "capturado_en_utc"},
        "capturado_en_utc": capturado,
    }


def escribir_bronce(cliente_gcs: storage.Client, config: ConfigGCP,
                    parte: ParteV2, ingestado_en: datetime) -> tuple[str, int]:
    """Sube la parte en P1 a bronce y devuelve su URI y sus filas."""
    tabla = a_p1(parte, ingestado_en)
    if tabla.num_rows != parte.filas:
        raise ErrorPartes(f"{parte.ruta}: {tabla.num_rows} filas, el JSON "
                          f"declara {parte.filas}")
    buffer = io.BytesIO()
    pq.write_table(tabla, buffer, compression="snappy")
    # El nombre lleva la corrida porque en bronce la partición es solo
    # tienda/anio_mes: un nivel corrida= rompería el hive partitioning.
    corrida = parte.ruta.split("/")[-2].removeprefix("corrida=")
    nombre = f"{corrida}_{parte.nombre}"
    uri = config.uri_bronce(parte.tienda, parte.anio_mes, nombre)
    objeto = uri.removeprefix(f"gs://{config.bucket_bronce}/")
    cliente_gcs.bucket(config.bucket_bronce).blob(objeto).upload_from_string(
        buffer.getvalue(), content_type="application/vnd.apache.parquet",
        retry=REINTENTO_SUBIDA)
    return uri, tabla.num_rows


def ejecutar(
    cliente_bq: bigquery.Client,
    cliente_gcs: storage.Client,
    config: ConfigGCP,
    origen: str,
    tabla_manifest: str | None = None,
    tabla_corridas: str | None = None,
) -> ResultadoV2:
    """Lleva a bronce las corridas completas y registra manifest y corridas."""
    sistema, raiz, corridas = descubrir(origen)
    estado = manifest.leer_estado(cliente_bq, config, tabla_manifest)
    ingestado_en = datetime.now(UTC)
    filas_manifest: list[manifest.FilaManifest] = []
    procesadas, saltadas, fallidas, omitidas = [], [], [], []

    for corrida in corridas:
        if not corrida.completa:
            omitidas.append(corrida.carpeta)
            continue
        try:
            partes = leer_partes(sistema, raiz, corrida)
        except ErrorPartes as e:
            fallidas.append((corrida.carpeta, str(e)))
            continue
        for parte in partes:
            decision = manifest.decidir(parte, estado)
            if not decision.sube:
                saltadas.append(parte.ruta)
                continue
            try:
                uri, filas = escribir_bronce(cliente_gcs, config, parte,
                                             ingestado_en)
            except ErrorPartes as e:
                fallidas.append((parte.ruta, str(e)))
                continue
            except Exception as e:  # noqa: BLE001 - una parte no tumba la corrida
                filas_manifest.append(_fila(parte, decision,
                                            manifest.ESTADO_ERROR, None, None))
                fallidas.append((parte.ruta, str(e)))
                continue
            filas_manifest.append(_fila(parte, decision, manifest.ESTADO_OK,
                                        uri, filas))
            procesadas.append(parte.ruta)

    manifest.registrar(cliente_bq, config, filas_manifest, tabla_manifest)
    cargados = registrar_corridas(cliente_bq, config, corridas, tabla_corridas)
    return ResultadoV2(tuple(procesadas), tuple(saltadas), tuple(fallidas),
                       tuple(omitidas), cargados)


def _fila(parte: ParteV2, decision: manifest.Decision, estado: str,
          uri_bronce: str | None, filas_bronce: int | None,
          ) -> manifest.FilaManifest:
    return manifest.FilaManifest(
        ruta_origen=parte.ruta, tienda=parte.tienda, anio_mes=parte.anio_mes,
        md5_origen=parte.md5, estado=estado, version=decision.version,
        bytes_origen=len(parte.contenido), filas_origen=parte.filas,
        uri_bronce=uri_bronce, filas_bronce=filas_bronce,
        variante_schema=VARIANTE)


def registrar_corridas(cliente: bigquery.Client, config: ConfigGCP,
                       corridas: list[Corrida],
                       tabla: str | None = None) -> int:
    """Carga los ``_corrida.json`` que aún no están; devuelve cuántos cargó.

    Append-only como el manifest: un JSON ya cargado con el mismo MD5 se
    salta, y uno que cambió (un parcial que luego terminó) entra como fila
    nueva.
    """
    ref = config.tabla_ops(tabla or TABLA_CORRIDAS)
    cliente.create_table(bigquery.Table(ref, schema=list(ESQUEMA_CORRIDAS)),
                         exists_ok=True)
    ya = {(f["corrida_id"], f["md5_json"]) for f in cliente.query(
        f"SELECT corrida_id, md5_json FROM `{ref}`").result()}
    ahora = datetime.now(UTC).isoformat()
    nuevas = [_fila_corrida(c, ahora) for c in corridas
              if (c.datos["corrida_id"], c.md5_json) not in ya]
    if nuevas:
        job = bigquery.LoadJobConfig(
            schema=list(ESQUEMA_CORRIDAS),
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND)
        cliente.load_table_from_json(nuevas, ref, job_config=job).result()
    return len(nuevas)


def _fila_corrida(corrida: Corrida, cargado_en: str) -> dict:
    datos = corrida.datos
    campos = {campo.name for campo in ESQUEMA_CORRIDAS}
    fila = {clave: valor for clave, valor in datos.items() if clave in campos}
    fila.update({
        "anio_mes": corrida.anio_mes,
        "respuestas_por_status": json.dumps(
            datos.get("respuestas_por_status") or {}),
        "ruta_json": f"{PREFIJO_RUTA}/{corrida.carpeta}/_corrida.json",
        "md5_json": corrida.md5_json,
        "cargado_en": cargado_en,
    })
    return fila
