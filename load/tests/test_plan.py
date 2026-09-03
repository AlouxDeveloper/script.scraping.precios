"""El dry-run: qué se subiría, a dónde, y qué se salta."""

import sys

import pytest
from typer.testing import CliRunner

from precios_load.cli import app
from precios_load.config import ArchivoDeclarado, ConfigGCP
from precios_load.descubrimiento import ArchivoFuente, Descubrimiento
from precios_load.plan import SALTA, SUBE, construir_plan, formato_bytes, render

CONFIG = ConfigGCP(
    project_id="proyecto-de-prueba",
    location="US",
    bucket_raw="raw_precios_bitek",
    bucket_bronce="bronce_precios_bitek",
    prefijo="precios",
    dataset="precios_raw",
    conexion_biglake="precios_biglake",
    ruta_local_datos="./salida/data",
    anio_mes_maximo="2026-08",
)

runner = CliRunner()


def fuente(ruta, tienda, anio_mes, filas=100, bytes_=2048, variante="V1", **extra):
    declarado = ArchivoDeclarado(ruta=ruta, tienda=tienda, anio_mes=anio_mes, **extra)
    return ArchivoFuente(
        ruta=ruta,
        tienda=tienda,
        anio_mes=anio_mes,
        bytes=bytes_,
        md5="0" * 32,
        filas=filas,
        variante=variante,
        declarado=declarado,
    )


HEB = fuente("2026/06_junio/scraping_detalle_heb.csv", "heb", "2026-06", filas=1000, bytes_=50_000)
YZA = fuente("2026/06_junio/scraping_detalle_yza.csv", "yza", "2026-06", filas=0, bytes_=77)
GI = fuente(
    "2026/07_julio/scraping_detalles_gi.csv", "gi", "2026-07", filas=500,
    copia_de="2026/06_junio/scraping_detalles_gi.csv",
)

DESCUBRIMIENTO = Descubrimiento(
    archivos=(HEB, YZA, GI),
    faltantes=("2026/07_julio/scraping_detalle_klyns.csv",),
    fuera_de_rango=("2026/09_septiembre/scraping_detalle_alsuper.csv",),
    hasta="2026-08",
)

DECLARADOS = [
    HEB.declarado,
    YZA.declarado,
    GI.declarado,
    ArchivoDeclarado(
        ruta="2026/07_julio/scraping_detalle_klyns.csv", tienda="klyns", anio_mes="2026-07"
    ),
    ArchivoDeclarado(
        ruta="2026/09_septiembre/scraping_detalle_alsuper.csv",
        tienda="alsuper",
        anio_mes="2026-09",
    ),
]


def plan_de(**filtros):
    return construir_plan(DESCUBRIMIENTO, CONFIG, DECLARADOS, **filtros)


# --- Destinos ---------------------------------------------------------------


def test_cada_archivo_lleva_su_destino_en_raw_y_en_bronce():
    entrada = plan_de().entradas[0]

    assert entrada.uri_raw == (
        "gs://raw_precios_bitek/precios/tienda=heb/anio_mes=2026-06"
        "/scraping_detalle_heb.csv"
    )
    assert entrada.uri_bronce == (
        "gs://bronce_precios_bitek/precios/tienda=heb/anio_mes=2026-06"
        "/scraping_detalle_heb.parquet"
    )


def test_el_parquet_hereda_el_nombre_del_csv():
    assert plan_de().entradas[2].uri_bronce.endswith("scraping_detalles_gi.parquet")


# --- Acción y motivo --------------------------------------------------------


def test_un_archivo_con_filas_se_sube():
    entrada = plan_de().entradas[0]
    assert entrada.accion == SUBE
    assert entrada.motivo == ""
    assert entrada.sube is True


def test_un_archivo_vacio_se_salta_con_motivo():
    entrada = plan_de().entradas[1]
    assert entrada.accion == SALTA
    assert entrada.motivo == "sin filas"
    assert "VACIO" in entrada.flags


def test_los_flags_salen_del_inventario():
    assert plan_de().entradas[2].flags == ("SOSPECHA_COPIA",)

    sin_header = fuente(
        "2026/06_junio/x.csv", "heb", "2026-06", variante="V4",
        sin_header=True, columnas=("SKU",), columnas_descartar=("NDF",),
    )
    entradas = construir_plan(
        Descubrimiento(archivos=(sin_header,), faltantes=(), hasta="2026-08"),
        CONFIG,
        [sin_header.declarado],
    ).entradas
    assert entradas[0].flags == ("SIN_HEADER", "DESCARTA:NDF")


# --- Totales y desglose -----------------------------------------------------


def test_los_totales_solo_cuentan_lo_que_se_sube():
    """El archivo vacío no suma filas ni bytes."""
    assert plan_de().totales() == (2, 1500, 50_000 + 2048)


def test_desglose_por_tienda_y_por_mes():
    """El desglose cuenta todo lo que hay; el resumen dice qué se sube."""
    plan = plan_de()
    assert plan.por("tienda") == {
        "gi": (1, 500, 2048),
        "heb": (1, 1000, 50_000),
        "yza": (1, 0, 77),
    }
    assert plan.por("anio_mes") == {
        "2026-06": (2, 1000, 50_077),
        "2026-07": (1, 500, 2048),
    }


# --- Filtros ----------------------------------------------------------------


def test_filtro_por_tienda():
    plan = plan_de(tienda="heb")
    assert [e.fuente.ruta for e in plan.entradas] == [HEB.ruta]
    assert plan.faltantes == () and plan.fuera_de_rango == ()


def test_filtro_por_mes():
    plan = plan_de(mes="2026-07")
    assert [e.fuente.ruta for e in plan.entradas] == [GI.ruta]
    assert plan.faltantes == ("2026/07_julio/scraping_detalle_klyns.csv",)


def test_los_dos_filtros_juntos():
    assert plan_de(tienda="gi", mes="2026-06").entradas == ()


def test_el_filtro_alcanza_a_los_fuera_de_rango():
    assert plan_de(mes="2026-09").fuera_de_rango == (
        "2026/09_septiembre/scraping_detalle_alsuper.csv",
    )
    assert plan_de(tienda="alsuper").fuera_de_rango == (
        "2026/09_septiembre/scraping_detalle_alsuper.csv",
    )


# --- Render -----------------------------------------------------------------


def test_el_render_nombra_corte_totales_y_pendientes():
    salida = "\n".join(render(plan_de(), CONFIG))

    assert "corte 2026-08 (inclusive)" in salida
    assert "se subirían  2 archivos  1,500 filas" in salida
    assert "se saltarían 1 archivo" in salida
    assert "scraping_detalle_klyns.csv" in salida
    assert "Para incluirlos: --hasta 2026-09" in salida


def test_el_resumen_omite_el_detalle_por_archivo():
    completo = "\n".join(render(plan_de(), CONFIG))
    breve = "\n".join(render(plan_de(), CONFIG, resumen=True))

    assert "ARCHIVOS (3)" in completo
    assert "ARCHIVOS" not in breve
    assert "RESUMEN" in breve and "POR TIENDA" in breve


def test_sin_resultados_lo_dice():
    assert "Ningún archivo cumple los filtros." in "\n".join(
        render(plan_de(tienda="fantasma"), CONFIG)
    )


@pytest.mark.parametrize(
    "n,esperado",
    [(77, "77 B"), (2048, "2.0 KB"), (2_570_907, "2.5 MB"), (2**30, "1.0 GB")],
)
def test_formato_de_bytes(n, esperado):
    assert formato_bytes(n) == esperado


# --- El comando -------------------------------------------------------------


def test_plan_corre_sin_tocar_google_cloud():
    """Ni credenciales ni red: nada del SDK de Google se llega a importar."""
    previos = {m for m in sys.modules if m.startswith("google")}

    resultado = runner.invoke(app, ["plan", "--resumen"])

    assert resultado.exit_code == 0, resultado.output
    assert "Plan de ingesta" in resultado.stdout
    assert {m for m in sys.modules if m.startswith("google")} == previos


def test_plan_avisa_si_el_mes_pedido_queda_fuera_del_corte():
    resultado = runner.invoke(app, ["plan", "--mes", "2026-09", "--resumen"])

    assert resultado.exit_code == 0
    assert "--hasta 2026-09" in resultado.output


@pytest.mark.parametrize("flag,valor", [("--hasta", "2026-9"), ("--mes", "26-08")])
def test_un_mes_mal_escrito_detiene_el_comando(flag, valor):
    """`"2026-09" <= "2026-9"`: sin validar, un typo deja pasar el mes abierto."""
    resultado = runner.invoke(app, ["plan", flag, valor, "--resumen"])

    assert resultado.exit_code == 1
    assert "se esperaba el formato YYYY-MM" in resultado.output


def test_una_tienda_inexistente_detiene_el_comando():
    """Un plan vacío por typo es indistinguible de 'ya no queda nada'."""
    resultado = runner.invoke(app, ["plan", "--tienda", "sorianaX", "--resumen"])

    assert resultado.exit_code == 1
    assert "no está en archivos.yml" in resultado.output
    assert "soriana" in resultado.output


def test_plan_con_hasta_amplia_el_corte():
    resultado = runner.invoke(app, ["plan", "--mes", "2026-09", "--hasta", "2026-09"])

    assert resultado.exit_code == 0
    assert "corte 2026-09 (inclusive)" in resultado.stdout
