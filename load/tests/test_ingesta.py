"""El orquestador de `ingesta`: fase raw + escritura del manifest.

Integración real: sube a `gs://<bucket_raw>/tienda=__test__/` y escribe en una
tabla de manifest desechable. Todo se limpia en el teardown.
"""

import threading

from typer.testing import CliRunner

from tests.conftest import HEADER_SOLO_CSV, csv_valido, fuente_falsa

from precios_load import bronce, cli, ingesta, manifest
from precios_load.cli import app
from precios_load.plan import SUBE, EntradaPlan

runner = CliRunner()


class _GCSNoObjetos:
    """cliente_gcs de mentira: ningún objeto existe todavía en la capa raw.

    Deja que `manifest.decidir` corra su red de seguridad sin tocar Google Cloud.
    """

    def bucket(self, _nombre):
        return self

    def get_blob(self, _objeto):
        return None


def _entrada(fuente, flags=()) -> EntradaPlan:
    return EntradaPlan(
        fuente=fuente,
        uri_raw="",
        uri_bronce="",
        accion=SUBE,
        motivo="",
        flags=tuple(flags),
    )


def _uri(cfg, fuente):
    return cfg.uri_raw(fuente.tienda, fuente.anio_mes, fuente.nombre)


def _uri_bronce(cfg, fuente):
    import os

    nombre = os.path.splitext(fuente.nombre)[0] + ".parquet"
    return cfg.uri_bronce(fuente.tienda, fuente.anio_mes, nombre)


def test_ejecutar_sube_archivo_nuevo_y_registra_fila_ok(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, limpiar_bronce, tabla_manifest_tmp
):
    contenido = csv_valido(2)
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))
    limpiar_bronce(_uri_bronce(cfg_gcp, fuente))

    resultado = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)],
        base=base, tabla=tabla_manifest_tmp,
    )

    assert resultado.procesados == (fuente.ruta,)
    assert resultado.fallidos == ()

    fila = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)[fuente.ruta]
    assert fila.estado == manifest.ESTADO_OK
    assert fila.uri_raw == _uri(cfg_gcp, fuente)
    assert fila.filas_origen == 2
    assert fila.bytes_origen == len(contenido)
    assert fila.uri_bronce == _uri_bronce(cfg_gcp, fuente)
    assert fila.filas_bronce == 2
    assert fila.version == 1


def test_ejecutar_dos_veces_la_segunda_salta_sin_escribir(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, limpiar_bronce, tabla_manifest_tmp
):
    contenido = csv_valido(1)
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))
    limpiar_bronce(_uri_bronce(cfg_gcp, fuente))

    comun = dict(base=base, tabla=tabla_manifest_tmp)
    ingesta.ejecutar(cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)], **comun)
    segunda = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)], **comun
    )

    assert segunda.saltados == (fuente.ruta,)
    assert segunda.procesados == ()
    fila = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)[fuente.ruta]
    assert fila.version == 1  # no incrementó


def test_dos_rutas_con_el_mismo_md5_producen_dos_filas(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, tabla_manifest_tmp
):
    """El caso de los dos archivos vacíos de septiembre: mismo hash, rutas distintas."""
    f1 = fuente_falsa(HEADER_SOLO_CSV, nombre="benavides.csv")
    f2 = fuente_falsa(HEADER_SOLO_CSV, nombre="fahorro.csv")
    assert f1.md5 == f2.md5

    base = base_local(f1, HEADER_SOLO_CSV)
    base_local(f2, HEADER_SOLO_CSV)
    limpiar_raw(_uri(cfg_gcp, f1))
    limpiar_raw(_uri(cfg_gcp, f2))

    resultado = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(f1), _entrada(f2)],
        base=base, tabla=tabla_manifest_tmp,
    )

    assert set(resultado.procesados) == {f1.ruta, f2.ruta}
    estado = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)
    assert estado[f1.ruta].estado == manifest.ESTADO_VACIO
    assert estado[f2.ruta].estado == manifest.ESTADO_VACIO
    # Un archivo vacío no genera Parquet.
    assert estado[f1.ruta].uri_bronce is None and estado[f1.ruta].filas_bronce is None
    assert estado[f2.ruta].uri_bronce is None


def test_una_subida_fallida_deja_fila_error_y_no_frena_al_resto(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, limpiar_bronce,
    tabla_manifest_tmp, monkeypatch
):
    ok = fuente_falsa(csv_valido(1), nombre="ok.csv")
    mala = fuente_falsa(csv_valido(1), nombre="mala.csv")
    base = base_local(ok, csv_valido(1))
    base_local(mala, csv_valido(1))
    limpiar_raw(_uri(cfg_gcp, ok))
    limpiar_bronce(_uri_bronce(cfg_gcp, ok))

    real = ingesta.raw.subir

    def flaky(cliente, cfg, fuente, base=None):
        if fuente.nombre == "mala.csv":
            raise ingesta.raw.ErrorSubidaRaw("boom")
        return real(cliente, cfg, fuente, base=base)

    monkeypatch.setattr(ingesta.raw, "subir", flaky)

    resultado = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(ok), _entrada(mala)],
        base=base, tabla=tabla_manifest_tmp,
    )

    assert resultado.procesados == (ok.ruta,)
    assert [ruta for ruta, _ in resultado.fallidos] == [mala.ruta]

    estado = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)
    assert estado[ok.ruta].estado == manifest.ESTADO_OK
    assert estado[mala.ruta].estado == manifest.ESTADO_ERROR
    assert estado[mala.ruta].uri_raw is None


def test_reconciliacion_fallida_no_deja_fila_en_el_manifest(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, tabla_manifest_tmp, monkeypatch
):
    """Descuadre de conteos: se reporta con ambos números, sin fila en el manifest."""
    contenido = csv_valido(2)
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))

    def descuadre(*a, **k):
        raise bronce.ErrorReconciliacion(
            f"{fuente.ruta}: el Parquet tiene 1 filas, el CSV de origen tiene 2"
        )

    monkeypatch.setattr(ingesta.bronce, "escribir", descuadre)

    resultado = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)],
        base=base, tabla=tabla_manifest_tmp,
    )

    assert resultado.procesados == ()
    assert [ruta for ruta, _ in resultado.fallidos] == [fuente.ruta]
    mensaje = resultado.fallidos[0][1]
    assert "1" in mensaje and "2" in mensaje and fuente.ruta in mensaje

    # Nada en el manifest: la próxima corrida lo reintenta limpio.
    assert fuente.ruta not in manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)
    # Raw sí quedó subido (es la fuente inmutable).
    objeto = _uri(cfg_gcp, fuente).removeprefix(f"gs://{cfg_gcp.bucket_raw}/")
    assert cliente_gcs.bucket(cfg_gcp.bucket_raw).blob(objeto).exists()


def test_un_fallo_de_subida_si_deja_fila_error(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, tabla_manifest_tmp, monkeypatch
):
    """A diferencia de la reconciliación, un fallo de red se reintenta: fila ERROR."""
    contenido = csv_valido(2)
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))

    def boom(*a, **k):
        raise RuntimeError("503 desde GCS")

    monkeypatch.setattr(ingesta.bronce, "escribir", boom)

    ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)],
        base=base, tabla=tabla_manifest_tmp,
    )

    fila = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)[fuente.ruta]
    assert fila.estado == manifest.ESTADO_ERROR
    assert fila.uri_raw == _uri(cfg_gcp, fuente)


def test_una_fila_error_previa_se_reintenta(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, limpiar_bronce, tabla_manifest_tmp
):
    contenido = csv_valido(1)
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))
    limpiar_bronce(_uri_bronce(cfg_gcp, fuente))

    manifest.registrar(
        cliente_bq,
        cfg_gcp,
        [
            manifest.FilaManifest(
                ruta_origen=fuente.ruta,
                tienda=fuente.tienda,
                anio_mes=fuente.anio_mes,
                md5_origen=fuente.md5,
                estado=manifest.ESTADO_ERROR,
                version=1,
            )
        ],
        tabla=tabla_manifest_tmp,
    )

    resultado = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)],
        base=base, tabla=tabla_manifest_tmp,
    )

    assert resultado.procesados == (fuente.ruta,)
    fila = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)[fuente.ruta]
    assert fila.estado == manifest.ESTADO_OK
    assert fila.version == 2


# --- Subida en paralelo -----------------------------------------------


def test_las_subidas_corren_en_paralelo(cfg_gcp, monkeypatch):
    """Dos archivos suben a la vez: en secuencial la barrera nunca se completaría."""
    barrera = threading.Barrier(2, timeout=5)

    monkeypatch.setattr(ingesta.manifest, "leer_estado", lambda *a, **k: {})
    monkeypatch.setattr(ingesta.manifest, "registrar", lambda *a, **k: None)

    def raw_con_barrera(cliente, config, fuente, base=None):
        barrera.wait()
        return f"gs://raw/{fuente.nombre}"

    monkeypatch.setattr(ingesta.raw, "subir", raw_con_barrera)
    monkeypatch.setattr(
        ingesta.bronce, "escribir", lambda *a, **k: ("gs://bronce/x.parquet", 1)
    )

    f1 = fuente_falsa(csv_valido(1), nombre="a.csv")
    f2 = fuente_falsa(csv_valido(1), nombre="b.csv")

    resultado = ingesta.ejecutar(
        None, _GCSNoObjetos(), cfg_gcp, [_entrada(f1), _entrada(f2)], trabajadores=2
    )

    assert set(resultado.procesados) == {f1.ruta, f2.ruta}
    assert resultado.fallidos == ()


def test_conserva_el_orden_de_entrada_con_resultados_mezclados(cfg_gcp, monkeypatch):
    """El paralelismo no altera el orden: los resultados salen como entraron."""
    saltado = fuente_falsa(csv_valido(1), nombre="saltado.csv")
    ok = fuente_falsa(csv_valido(2), nombre="ok.csv")
    malo = fuente_falsa(csv_valido(2), nombre="malo.csv")

    estado = {
        saltado.ruta: manifest.FilaManifest(
            ruta_origen=saltado.ruta,
            tienda=saltado.tienda,
            anio_mes=saltado.anio_mes,
            md5_origen=saltado.md5,
            estado=manifest.ESTADO_OK,
            version=1,
            uri_bronce="gs://bronce/saltado.parquet",
        )
    }
    monkeypatch.setattr(ingesta.manifest, "leer_estado", lambda *a, **k: estado)
    monkeypatch.setattr(ingesta.manifest, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(
        ingesta.raw, "subir", lambda cl, cfg, f, base=None: f"gs://raw/{f.nombre}"
    )

    def escribir(cliente, config, fuente, base=None, ingestado_en=None):
        if fuente.nombre == "malo.csv":
            raise bronce.ErrorReconciliacion(
                f"{fuente.ruta}: el Parquet tiene 1 filas, el CSV de origen tiene 2"
            )
        return f"gs://bronce/{fuente.nombre}", fuente.filas

    monkeypatch.setattr(ingesta.bronce, "escribir", escribir)

    entradas = [_entrada(saltado), _entrada(ok), _entrada(malo)]
    resultado = ingesta.ejecutar(
        None, _GCSNoObjetos(), cfg_gcp, entradas, trabajadores=4
    )

    assert resultado.saltados == (saltado.ruta,)
    assert resultado.procesados == (ok.ruta,)
    assert [r for r, _ in resultado.fallidos] == [malo.ruta]


# --- El comando `ingesta` ----------------------------------------------


def test_comando_ingesta_pasa_el_plan_filtrado_al_orquestador(
    datos_reales, monkeypatch
):
    """El comando arma el plan, aplica --tienda/--mes y delega en ejecutar()."""
    visto = {}

    def fake_ejecutar(cliente_bq, cliente_gcs, config, entradas, base=None, tabla=None):
        visto["rutas"] = [e.fuente.ruta for e in entradas]
        return ingesta.ResultadoIngesta(
            procesados=tuple(visto["rutas"]), saltados=(), fallidos=()
        )

    monkeypatch.setattr(cli, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(cli, "cliente_bq", lambda cfg: None)
    monkeypatch.setattr(cli, "cliente_gcs", lambda cfg: None)

    resultado = runner.invoke(app, ["ingesta", "--tienda", "chedraui", "--mes", "2026-08"])

    assert resultado.exit_code == 0, resultado.output
    assert visto["rutas"], "no se pasó ninguna entrada"
    assert all("chedraui" in r and "08_agosto" in r for r in visto["rutas"])
    assert "1" in resultado.stdout  # el resumen menciona algún conteo
