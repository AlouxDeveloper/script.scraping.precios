"""Puerta de calidad: `plan` contra el histórico completo, sin sorpresas.

Concilia la salida del dry-run con el inventario conocido. Si algo aquí falla,
el problema está en `archivos.yml` o en un parser, y hay que arreglarlo antes
de subir un solo byte a Google Cloud.

Corre sobre el histórico en disco: septiembre aún no ha cerrado, sus archivos
no están en disco ni declarados. Cuando entre, se re-agregan las 6 entradas
(con sus 2 casos vacíos) y se reactiva `test_los_dos_archivos_vacios`.
"""

import pytest

from precios_load.config import cargar_config
from precios_load.descubrimiento import descubrir
from precios_load.plan import construir_plan

TODO_EL_HISTORICO = "2026-08"

TOTAL_ARCHIVOS = 134
TOTAL_FILAS = 987461
TOTAL_BYTES = 370891023

FILAS_POR_MES = {
    "2025-12": 18773, "2026-01": 25320, "2026-02": 138627, "2026-03": 142103,
    "2026-04": 130294, "2026-05": 135526, "2026-06": 119023, "2026-07": 143466,
    "2026-08": 134329,
}

ARCHIVOS_POR_MES = {
    "2025-12": 4, "2026-01": 8, "2026-02": 15, "2026-03": 17, "2026-04": 15,
    "2026-05": 18, "2026-06": 19, "2026-07": 19, "2026-08": 19,
}

POR_VARIANTE = {"V1": 89, "V2": 27, "V3": 15, "V4": 1, "V5": 1, "V6": 1}

TIENDAS = {
    "alsuper", "aurrera", "benavides", "chedraui", "comer", "fahorro",
    "farmalisto", "farmatodo", "fesa", "gi", "guadalajara", "heb", "isseg",
    "klyns", "sanpablo", "similares", "soriana", "walmart", "yza",
}

VACIOS: set[str] = set()  # septiembre pendiente de cierre: sin archivos vacíos en disco

# Archivo -> (filas desfasadas, filas del archivo, mes mayoritario de las fechas).
DESFASES = {
    "2026/01_enero/scraping_detalle_heb.csv": (8, 8, "2026-02"),
    "2026/03_marzo/scraping_detalle_fesa.csv": (5, 7576, "2026-03"),
    "2026/03_marzo/scraping_detalles_sanpablo.csv": (5937, 5937, "2026-04"),
    "2026/04_abril/scraping_detalle_walmart.csv": (35834, 35834, "2026-03"),
    "2026/06_junio/scraping_detalle_aurrera.csv": (732, 4822, "2026-06"),
}

COPIAS = 9


@pytest.fixture(scope="module")
def plan(datos_reales, declarados):
    descubrimiento = descubrir(declarados=declarados, hasta=TODO_EL_HISTORICO)
    return construir_plan(descubrimiento, cargar_config(), declarados)


def flags_de(entrada, prefijo: str) -> str | None:
    for flag in entrada.flags:
        if flag.split(":")[0] == prefijo:
            return flag
    return None


# --- Los totales ------------------------------------------------------------


def test_los_134_archivos_estan_clasificados(plan):
    assert len(plan.entradas) == TOTAL_ARCHIVOS
    assert plan.faltantes == ()
    assert plan.fuera_de_rango == ()


def test_cero_esquemas_desconocidos(plan):
    """Un header desconocido habría abortado el descubrimiento nombrando el archivo."""
    assert all(e.fuente.variante in POR_VARIANTE for e in plan.entradas)


def test_el_total_de_filas(plan):
    assert sum(e.fuente.filas for e in plan.entradas) == TOTAL_FILAS


def test_el_total_de_bytes(plan):
    assert sum(e.fuente.bytes for e in plan.entradas) == TOTAL_BYTES


# --- El reparto -------------------------------------------------------------


def test_las_filas_por_mes(plan):
    assert {mes: filas for mes, (_, filas, _) in plan.por("anio_mes").items()} == FILAS_POR_MES


def test_los_archivos_por_mes(plan):
    assert {
        mes: archivos for mes, (archivos, _, _) in plan.por("anio_mes").items()
    } == ARCHIVOS_POR_MES


def test_la_distribucion_de_variantes(plan):
    conteo = {}
    for e in plan.entradas:
        conteo[e.fuente.variante] = conteo.get(e.fuente.variante, 0) + 1
    assert conteo == POR_VARIANTE


def test_las_19_tiendas_sin_slugs_inventados(plan):
    assert set(plan.por("tienda")) == TIENDAS


# --- Las anomalías conocidas ------------------------------------------------


@pytest.mark.skip(reason="septiembre pendiente de cierre: sin archivos vacíos en disco")
def test_los_dos_archivos_vacios(plan):
    vacios = {e.fuente.ruta for e in plan.entradas if e.fuente.vacio}
    assert vacios == VACIOS
    assert all(e.accion == "salta" for e in plan.entradas if e.fuente.vacio)


def test_los_9_archivos_con_sospecha_de_copia(plan):
    marcados = [e for e in plan.entradas if flags_de(e, "SOSPECHA_COPIA")]
    assert len(marcados) == COPIAS
    assert all(e.fuente.declarado.copia_de for e in marcados)


def test_los_5_archivos_con_desfase_de_mes(plan):
    desfasados = {
        e.fuente.ruta: (e.fuente.filas_desfasadas, e.fuente.filas, e.fuente.anio_mes_dato)
        for e in plan.entradas
        if e.fuente.desfase
    }
    assert desfasados == DESFASES


def test_el_desfase_se_ve_en_los_flags(plan):
    por_ruta = {e.fuente.ruta: e for e in plan.entradas}

    # Todo el archivo es de otro mes: el flag nombra el mes mayoritario.
    walmart = por_ruta["2026/04_abril/scraping_detalle_walmart.csv"]
    assert flags_de(walmart, "DESFASE_MES") == "DESFASE_MES:35834→2026-03"

    # Solo unas filas sueltas: el mes mayoritario sigue siendo el de la carpeta.
    fesa = por_ruta["2026/03_marzo/scraping_detalle_fesa.csv"]
    assert flags_de(fesa, "DESFASE_MES") == "DESFASE_MES:5"


def test_el_reparto_entre_subir_y_saltar(plan):
    archivos, filas, bytes_ = plan.totales()

    # Sin archivos vacíos en disco, todo lo declarado se sube (septiembre
    # pendiente de cierre traería 2 archivos VACIO que restan de este total).
    assert archivos == TOTAL_ARCHIVOS - len(VACIOS)
    assert filas == TOTAL_FILAS
    assert bytes_ == TOTAL_BYTES - 77 * len(VACIOS)
