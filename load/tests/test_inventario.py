"""El inventario declarado debe cuadrar consigo mismo y con el disco."""

import os
import textwrap

import pytest
import yaml

from precios_load.config import (
    ErrorConfig,
    anio_mes_de_ruta,
    cargar_archivos,
    cargar_config,
)
from precios_load.rutas import raiz_repo

TIENDAS = {
    "alsuper", "aurrera", "benavides", "chedraui", "comer", "fahorro",
    "farmalisto", "farmatodo", "fesa", "gi", "guadalajara", "heb", "isseg",
    "klyns", "sanpablo", "similares", "soriana", "walmart", "yza",
}

# Copias detectadas comparando el contenido de cada archivo ignorando la
# columna de fecha: son idénticos salvo las fechas.
COPIAS = {
    "2026/03_marzo/scraping_detalle_soriana.csv": "2026/02_febrero/scraping_detalle_soriana.csv",
    "2026/03_marzo/scraping_detalles_gi.csv": "2026/02_febrero/scraping_detalles_gi.csv",
    "2026/05_mayo/scraping_detalle_aurrera1.csv": "2026/03_marzo/scraping_detalle_aurrera.csv",
    "2026/05_mayo/scraping_detalle_similares.csv": "2026/04_abril/scraping_detalle_similares.csv",
    "2026/05_mayo/scraping_detalle_soriana.csv": "2026/04_abril/scraping_detalle_soriana.csv",
    "2026/05_mayo/scraping_detalles_gi.csv": "2026/04_abril/scraping_detalles_gi.csv",
    "2026/06_junio/scraping_detalle_comer.csv": "2026/05_mayo/scraping_detalle_comer.csv",
    "2026/08_agosto/scraping_detalle_chedraui.csv": "2026/05_mayo/scraping_detalle_chedraui.csv",
    "2026/08_agosto/scraping_detalle_heb.csv": "2026/07_julio/scraping_detalle_heb.csv",
}

ARCHIVOS_POR_MES = {
    "2025-12": 4, "2026-01": 8, "2026-02": 15, "2026-03": 17, "2026-04": 15,
    "2026-05": 18, "2026-06": 19, "2026-07": 19, "2026-08": 18, "2026-09": 6,
}


@pytest.fixture(scope="module")
def inventario():
    return cargar_archivos()


def test_son_139_archivos_sin_rutas_repetidas(inventario):
    assert len(inventario) == 139
    assert len({a.ruta for a in inventario}) == 139


def test_las_19_tiendas_declaradas(inventario):
    assert {a.tienda for a in inventario} == TIENDAS


def test_reparto_por_mes(inventario):
    por_mes = {}
    for a in inventario:
        por_mes[a.anio_mes] = por_mes.get(a.anio_mes, 0) + 1
    assert por_mes == ARCHIVOS_POR_MES


def test_anomalias_estructurales(inventario):
    sin_header = [a for a in inventario if a.sin_header]
    assert [a.ruta for a in sin_header] == ["2026/06_junio/scraping_detalle_heb.csv"]
    assert len(sin_header[0].columnas) == 8

    descartes = [a for a in inventario if a.columnas_descartar]
    assert [a.ruta for a in descartes] == ["2026/06_junio/scraping_detalles_fahorro.csv"]
    assert descartes[0].columnas_descartar == ("NDF",)


def test_copias_declaradas(inventario):
    assert {a.ruta: a.copia_de for a in inventario if a.copia_de} == COPIAS


def test_la_copia_siempre_apunta_a_un_mes_anterior(inventario):
    por_ruta = {a.ruta: a for a in inventario}
    for a in inventario:
        if a.copia_de:
            assert por_ruta[a.copia_de].anio_mes < a.anio_mes, a.ruta


def test_anio_mes_sale_de_la_carpeta():
    assert anio_mes_de_ruta("2025/diciembre/productos_detalle_fesa.csv") == "2025-12"
    assert anio_mes_de_ruta("2026/03_marzo/scraping_detalle_aurrera.csv") == "2026-03"

    with pytest.raises(ErrorConfig, match="no corresponde a ningún mes"):
        anio_mes_de_ruta("2026/13_bruma/x.csv")


def test_el_inventario_coincide_con_el_disco(inventario):
    """`salida/` no está en el repo; si no existe localmente, se salta."""
    base = cargar_config().ruta_datos()
    if not os.path.isdir(base):
        pytest.skip("salida/data no existe en esta máquina")

    en_disco = {
        os.path.relpath(os.path.join(d, f), base).replace(os.sep, "/")
        for d, _, fs in os.walk(base)
        for f in fs
        if f.endswith(".csv")
    }
    declarados = {a.ruta for a in inventario}

    assert not (en_disco - declarados), "hay archivos en disco sin declarar"
    assert not (declarados - en_disco), "hay archivos declarados que no existen"


# --- Validación del formato -------------------------------------------------


def escribir(tmp_path, contenido, monkeypatch):
    (tmp_path / "load" / "config").mkdir(parents=True)
    (tmp_path / "load" / "config" / "archivos.yml").write_text(
        textwrap.dedent(contenido), encoding="utf-8"
    )
    monkeypatch.setattr("precios_load.config.raiz_repo", lambda: str(tmp_path))
    return "load/config/archivos.yml"


BASE = """
archivos:
  - ruta: 2026/03_marzo/scraping_detalle_soriana.csv
    tienda: soriana
    anio_mes: 2026-03
"""


def test_ruta_duplicada_falla(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, BASE + BASE.split("archivos:")[1], monkeypatch)
    with pytest.raises(ErrorConfig, match="dos veces"):
        cargar_archivos(ruta)


def test_anio_mes_que_no_cuadra_con_la_carpeta_falla(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, BASE.replace("2026-03", "2026-04"), monkeypatch)
    with pytest.raises(ErrorConfig, match="pero su carpeta dice '2026-03'"):
        cargar_archivos(ruta)


def test_clave_desconocida_falla(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, BASE + "    sospechoso: true\n", monkeypatch)
    with pytest.raises(ErrorConfig, match="sospechoso"):
        cargar_archivos(ruta)


def test_sin_header_sin_columnas_falla(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, BASE + "    sin_header: true\n", monkeypatch)
    with pytest.raises(ErrorConfig, match="no declara sus 'columnas'"):
        cargar_archivos(ruta)


def test_copia_de_inexistente_falla(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, BASE + "    copia_de: 2026/01_enero/fantasma.csv\n", monkeypatch)
    with pytest.raises(ErrorConfig, match="no está en el inventario"):
        cargar_archivos(ruta)


def test_columnas_como_escalar_falla(tmp_path, monkeypatch):
    """`columnas_descartar: NDF` se convertiría en ('N', 'D', 'F')."""
    ruta = escribir(tmp_path, BASE + "    columnas_descartar: NDF\n", monkeypatch)

    with pytest.raises(ErrorConfig, match="lista de nombres entre corchetes"):
        cargar_archivos(ruta)


def test_dos_rutas_que_escriben_el_mismo_destino_fallan(tmp_path, monkeypatch):
    """La ruta local es única, pero el destino en GCS es (tienda, mes, nombre)."""
    gemelo = """
  - ruta: 2026/3_marzo/scraping_detalle_soriana.csv
    tienda: soriana
    anio_mes: 2026-03
"""
    ruta = escribir(tmp_path, BASE + gemelo.lstrip("\n"), monkeypatch)

    with pytest.raises(ErrorConfig, match="escriben el mismo destino"):
        cargar_archivos(ruta)


def test_el_yaml_real_es_parseable():
    """Guarda contra un YAML sintácticamente roto por una edición a mano."""
    with open(os.path.join(raiz_repo(), "load/config/archivos.yml"), encoding="utf-8") as f:
        assert isinstance(yaml.safe_load(f)["archivos"], list)
