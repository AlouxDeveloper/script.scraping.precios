"""El orquestador de `ingesta`: fase raw + escritura del manifest.

Integración real: sube a `gs://<bucket_raw>/tienda=__test__/` y escribe en una
tabla de manifest desechable. Todo se limpia en el teardown.
"""

from typer.testing import CliRunner

from tests.conftest import HEADER_SOLO_CSV, fuente_falsa

from precios_load import cli, ingesta, manifest
from precios_load.cli import app
from precios_load.plan import SUBE, EntradaPlan

runner = CliRunner()


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


def test_ejecutar_sube_archivo_nuevo_y_registra_fila_ok(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, tabla_manifest_tmp
):
    contenido = b"sku,precio\n1,9.99\n2,5.00\n"
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))

    resultado = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)],
        base=base, tabla=tabla_manifest_tmp,
    )

    assert resultado.subidos == (fuente.ruta,)
    assert resultado.errores == ()

    fila = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)[fuente.ruta]
    assert fila.estado == manifest.ESTADO_OK
    assert fila.uri_raw == _uri(cfg_gcp, fuente)
    assert fila.filas_origen == 2
    assert fila.bytes_origen == len(contenido)
    assert fila.uri_bronce is None and fila.filas_bronce is None
    assert fila.version == 1


def test_ejecutar_dos_veces_la_segunda_salta_sin_escribir(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, tabla_manifest_tmp
):
    contenido = b"sku,precio\n1,9.99\n"
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))

    comun = dict(base=base, tabla=tabla_manifest_tmp)
    ingesta.ejecutar(cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)], **comun)
    segunda = ingesta.ejecutar(
        cliente_bq, cliente_gcs, cfg_gcp, [_entrada(fuente)], **comun
    )

    assert segunda.saltados == (fuente.ruta,)
    assert segunda.subidos == ()
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

    assert set(resultado.subidos) == {f1.ruta, f2.ruta}
    estado = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)
    assert estado[f1.ruta].estado == manifest.ESTADO_VACIO
    assert estado[f2.ruta].estado == manifest.ESTADO_VACIO


def test_una_subida_fallida_deja_fila_error_y_no_frena_al_resto(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, tabla_manifest_tmp, monkeypatch
):
    ok = fuente_falsa(b"a,b\n1,2\n", nombre="ok.csv")
    mala = fuente_falsa(b"c,d\n3,4\n", nombre="mala.csv")
    base = base_local(ok, b"a,b\n1,2\n")
    base_local(mala, b"c,d\n3,4\n")
    limpiar_raw(_uri(cfg_gcp, ok))

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

    assert resultado.subidos == (ok.ruta,)
    assert [ruta for ruta, _ in resultado.errores] == [mala.ruta]

    estado = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)
    assert estado[ok.ruta].estado == manifest.ESTADO_OK
    assert estado[mala.ruta].estado == manifest.ESTADO_ERROR
    assert estado[mala.ruta].uri_raw is None


def test_una_fila_error_previa_se_reintenta(
    cliente_bq, cliente_gcs, cfg_gcp, base_local, limpiar_raw, tabla_manifest_tmp
):
    contenido = b"x,y\n1,2\n"
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(_uri(cfg_gcp, fuente))

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

    assert resultado.subidos == (fuente.ruta,)
    fila = manifest.leer_estado(cliente_bq, cfg_gcp, tabla=tabla_manifest_tmp)[fuente.ruta]
    assert fila.estado == manifest.ESTADO_OK
    assert fila.version == 2


# --- El comando `ingesta` ----------------------------------------------


def test_comando_ingesta_pasa_el_plan_filtrado_al_orquestador(
    datos_reales, monkeypatch
):
    """El comando arma el plan, aplica --tienda/--mes y delega en ejecutar()."""
    visto = {}

    def fake_ejecutar(cliente_bq, cliente_gcs, config, entradas, base=None, tabla=None):
        visto["rutas"] = [e.fuente.ruta for e in entradas]
        return ingesta.ResultadoIngesta(
            subidos=tuple(visto["rutas"]), saltados=(), errores=()
        )

    monkeypatch.setattr(cli, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(cli, "cliente_bq", lambda cfg: None)
    monkeypatch.setattr(cli, "cliente_gcs", lambda cfg: None)

    resultado = runner.invoke(app, ["ingesta", "--tienda", "chedraui", "--mes", "2026-09"])

    assert resultado.exit_code == 0, resultado.output
    assert visto["rutas"], "no se pasó ninguna entrada"
    assert all("chedraui" in r and "09_septiembre" in r for r in visto["rutas"])
    assert "1" in resultado.stdout  # el resumen menciona algún conteo
