"""El manifest de ingesta: estado de idempotencia en BigQuery.

Integración real contra el dataset de `gcp.yml`. Cada test usa una tabla
desechable (`tabla_manifest_tmp`); `_ingesta_manifest` nunca se toca.
"""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from precios_load import manifest
from precios_load.cli import app
from precios_load.config import ArchivoDeclarado
from precios_load.descubrimiento import ArchivoFuente

runner = CliRunner()


def _fuente(
    ruta: str = "2026/06_junio/scraping_detalle_heb.csv", md5: str = "abc123", **extra
) -> ArchivoFuente:
    declarado = ArchivoDeclarado(ruta=ruta, tienda="heb", anio_mes="2026-06")
    base = dict(
        ruta=ruta,
        tienda="heb",
        anio_mes="2026-06",
        bytes=2048,
        md5=md5,
        filas=100,
        variante="V4",
        declarado=declarado,
    )
    return ArchivoFuente(**{**base, **extra})


def _fila(ruta: str, md5: str, version: int, **extra) -> manifest.FilaManifest:
    base = dict(
        ruta_origen=ruta,
        tienda="heb",
        anio_mes="2026-06",
        md5_origen=md5,
        estado=manifest.ESTADO_OK,
        version=version,
    )
    return manifest.FilaManifest(**{**base, **extra})


# --- Crear la tabla --------------------------------------------------------


def test_crear_tabla_es_idempotente(cliente_bq, cfg_gcp, tabla_manifest_tmp):
    """Ejecutarlo dos veces no falla ni redefine la tabla."""
    creada = manifest.crear_tabla(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)
    de_nuevo = manifest.crear_tabla(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)

    assert creada is True
    assert de_nuevo is False


def test_la_tabla_creada_tiene_el_esquema_declarado(cliente_bq, cfg_gcp, tabla_manifest_tmp):
    manifest.crear_tabla(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)

    tabla = cliente_bq.get_table(cfg_gcp.tabla(tabla_manifest_tmp))
    assert [(c.name, c.field_type, c.mode) for c in tabla.schema] == [
        (c.name, c.field_type, c.mode) for c in manifest.ESQUEMA_MANIFEST
    ]


# --- Escribir y releer el estado -----------------------------------------


def test_leer_estado_sin_tabla_la_crea_y_devuelve_vacio(cliente_bq, cfg_gcp, tabla_manifest_tmp):
    estado = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)

    assert estado == {}
    assert cliente_bq.get_table(cfg_gcp.tabla(tabla_manifest_tmp))  # la creó


def test_registrar_y_leer_estado_round_trip(cliente_bq, cfg_gcp, tabla_manifest_tmp):
    fila = _fila(
        "2026/06_junio/scraping_detalle_heb.csv",
        "abc123",
        1,
        bytes_origen=2048,
        filas_origen=100,
        filas_bronce=100,
        uri_raw="gs://raw/x.csv",
        uri_bronce="gs://bronce/x.parquet",
        variante_schema="V4",
        flags=("DESFASE_MES",),
    )

    manifest.registrar(cliente_bq, cfg_gcp, [fila], tabla=tabla_manifest_tmp)
    estado = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)

    leida = estado["2026/06_junio/scraping_detalle_heb.csv"]
    assert leida.md5_origen == "abc123"
    assert leida.version == 1
    assert leida.estado == manifest.ESTADO_OK
    assert leida.filas_origen == 100
    assert leida.flags == ("DESFASE_MES",)
    assert leida.ingestado_en is not None


def test_registrar_es_atomico_si_una_fila_es_invalida_no_escribe_ninguna(
    cliente_bq, cfg_gcp, tabla_manifest_tmp
):
    """Un fallo a mitad no puede dejar el manifest con estado a medias."""
    invalida = manifest.FilaManifest(
        ruta_origen="rota.csv",
        tienda="heb",
        anio_mes="2026-06",
        md5_origen="m",
        estado=None,  # columna REQUIRED: el load job entero falla
        version=1,
    )

    with pytest.raises(Exception):  # noqa: B017 - basta con que aborte
        manifest.registrar(
            cliente_bq,
            cfg_gcp,
            [_fila("buena.csv", "m", 1), invalida],
            tabla=tabla_manifest_tmp,
        )

    assert manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp) == {}


def test_registrar_asigna_ingestado_en_si_falta(cliente_bq, cfg_gcp, tabla_manifest_tmp):
    antes = datetime.now(UTC)
    manifest.registrar(
        cliente_bq, cfg_gcp, [_fila("a/b.csv", "m1", 1)], tabla=tabla_manifest_tmp
    )

    leida = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)["a/b.csv"]
    assert leida.ingestado_en >= antes


def test_leer_estado_devuelve_solo_la_fila_de_mayor_version(
    cliente_bq, cfg_gcp, tabla_manifest_tmp
):
    """Append-only: una recarga añade v2, el estado actual la ignora a v1."""
    manifest.registrar(
        cliente_bq,
        cfg_gcp,
        [
            _fila("recargado.csv", "md5-viejo", 1),
            _fila("recargado.csv", "md5-nuevo", 2),
            _fila("intacto.csv", "md5-unico", 1),
        ],
        tabla=tabla_manifest_tmp,
    )

    estado = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)

    assert set(estado) == {"recargado.csv", "intacto.csv"}
    assert estado["recargado.csv"].md5_origen == "md5-nuevo"
    assert estado["recargado.csv"].version == 2


# --- Decidir qué hacer con un archivo (sin red) --------------------------


def test_decidir_archivo_nuevo_sube_en_version_1():
    decision = manifest.decidir(_fuente(md5="m1"), estado={})

    assert decision.accion == manifest.SUBIR
    assert decision.version == 1
    assert decision.fila_previa is None


def test_decidir_md5_sin_cambios_salta_sin_tocar_red():
    fuente = _fuente(md5="igual")
    estado = {fuente.ruta: _fila(fuente.ruta, "igual", 3)}

    decision = manifest.decidir(fuente, estado)

    assert decision.accion == manifest.SALTAR
    assert decision.version == 3


def test_decidir_md5_distinto_reprocesa_e_incrementa_version():
    fuente = _fuente(md5="nuevo")
    estado = {fuente.ruta: _fila(fuente.ruta, "viejo", 2)}

    decision = manifest.decidir(fuente, estado)

    assert decision.accion == manifest.SUBIR
    assert decision.version == 3
    assert decision.fila_previa.md5_origen == "viejo"


# --- Red de seguridad: manifest vacío pero el objeto ya está en GCS ------


@pytest.fixture
def subir_blob_raw(cliente_gcs, cfg_gcp):
    """Sube contenido a la ruta raw de un `ArchivoFuente` y lo borra al terminar."""
    creados = []

    def _subir(fuente: ArchivoFuente, contenido: bytes):
        objeto = cfg_gcp.uri_raw(
            fuente.tienda, fuente.anio_mes, fuente.nombre
        ).removeprefix(f"gs://{cfg_gcp.bucket_raw}/")
        blob = cliente_gcs.bucket(cfg_gcp.bucket_raw).blob(objeto)
        blob.upload_from_string(contenido)
        creados.append(blob)
        return blob

    yield _subir
    for blob in creados:
        blob.delete()


def _fuente_efimera(contenido: bytes) -> ArchivoFuente:
    ruta = f"2026/06_junio/__test_manifest_{uuid4().hex[:8]}.csv"
    return _fuente(ruta=ruta, md5=hashlib.md5(contenido).hexdigest())


def test_manifest_vacio_pero_objeto_en_gcs_con_mismo_md5_salta(
    cliente_gcs, cfg_gcp, subir_blob_raw
):
    contenido = b"sku,precio\n123,41.90\n"
    fuente = _fuente_efimera(contenido)
    subir_blob_raw(fuente, contenido)

    decision = manifest.decidir(fuente, {}, cliente_gcs=cliente_gcs, config=cfg_gcp)

    assert decision.accion == manifest.SALTAR
    assert decision.version == 1


def test_manifest_vacio_y_objeto_en_gcs_con_md5_distinto_sube(
    cliente_gcs, cfg_gcp, subir_blob_raw
):
    fuente = _fuente_efimera(b"contenido nuevo local")
    subir_blob_raw(fuente, b"contenido viejo en gcs")

    decision = manifest.decidir(fuente, {}, cliente_gcs=cliente_gcs, config=cfg_gcp)

    assert decision.accion == manifest.SUBIR
    assert decision.version == 1
    assert decision.fila_previa is None


def test_manifest_vacio_y_objeto_ausente_en_gcs_sube(cliente_gcs, cfg_gcp):
    fuente = _fuente_efimera(b"nunca subido")

    decision = manifest.decidir(fuente, {}, cliente_gcs=cliente_gcs, config=cfg_gcp)

    assert decision.accion == manifest.SUBIR
    assert decision.version == 1


# --- Resumen para el comando `estado` -----------------------------------


def test_resumen_de_manifest_vacio_no_falla(cliente_bq, cfg_gcp, tabla_manifest_tmp):
    lineas = manifest.resumen(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)

    assert any("0" in linea for linea in lineas)


def test_resumen_agrupa_por_estado_tienda_y_mes(cliente_bq, cfg_gcp, tabla_manifest_tmp):
    manifest.registrar(
        cliente_bq,
        cfg_gcp,
        [
            _fila("a.csv", "m", 1, estado=manifest.ESTADO_OK, filas_origen=100),
            _fila("b.csv", "m1", 1, estado=manifest.ESTADO_VACIO, filas_origen=0),
            _fila(
                "c.csv", "old", 1, tienda="soriana", anio_mes="2026-07",
                estado=manifest.ESTADO_OK, filas_origen=50,
            ),
            _fila(
                "c.csv", "new", 2, tienda="soriana", anio_mes="2026-07",
                estado=manifest.ESTADO_OK, filas_origen=50,
            ),
        ],
        tabla=tabla_manifest_tmp,
    )

    lineas = manifest.resumen(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)
    texto = "\n".join(lineas)

    # Estado actual: a, b, c (la recarga de c cuenta una sola vez).
    assert any(l.strip() == "archivos     3" for l in lineas)
    assert "recargados   1" in texto
    assert "OK 2" in texto and "VACIO 1" in texto
    assert "heb" in texto and "soriana" in texto
    assert "2026-06" in texto and "2026-07" in texto


# --- El comando `estado` ------------------------------------------------


def test_estado_imprime_el_resumen_del_manifest(
    cliente_bq, cfg_gcp, tabla_manifest_tmp, monkeypatch
):
    monkeypatch.setattr(manifest, "TABLA_MANIFEST", tabla_manifest_tmp)
    manifest.registrar(
        cliente_bq, cfg_gcp, [_fila("x/y.csv", "m", 1)], tabla=tabla_manifest_tmp
    )

    resultado = runner.invoke(app, ["estado"])

    assert resultado.exit_code == 0, resultado.output
    assert tabla_manifest_tmp in resultado.stdout  # usó la tabla monkeypatcheada
    assert "archivos     1" in resultado.stdout
    assert "heb" in resultado.stdout
