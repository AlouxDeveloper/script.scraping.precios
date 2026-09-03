"""El recorrido de `salida/data` y su cruce con el inventario declarado."""

import os

import pytest

from precios_load.bronce import md5_de_archivo
from precios_load.config import ArchivoDeclarado
from precios_load.descubrimiento import (
    ArchivoFuente,
    ErrorDescubrimiento,
    descubrir,
    rutas_en_disco,
)

HEADER_V1 = (
    "SKU,URL_PRODUCTO,Producto,Precio_Actual,Precio_Oferta,URL_IMAGEN,"
    "Fecha_Hora_Captura,Tienda\n"
)
FILA = "900437,https://heb.com.mx/x/p,Cubrebocas,41.90,41.90,https://img/1,2026-06-14 20:31:07,HEB\n"

RUTA_HEB = "2026/06_junio/scraping_detalle_heb.csv"
RUTA_YZA = "2026/06_junio/scraping_detalle_yza.csv"

# Reparto real del histórico en disco. Septiembre aún no ha cerrado: sus
# archivos no están en disco ni declarados en archivos.yml. Cuando entre, se
# re-agregan las 6 entradas (con sus 2 casos vacíos) y se reactivan los tests
# marcados con skip "septiembre pendiente de cierre".
TOTAL_ARCHIVOS = 134
TOTAL_FILAS = 987461
POR_VARIANTE = {"V1": 89, "V2": 27, "V3": 15, "V4": 1, "V5": 1, "V6": 1}

# El corte declarado en gcp.yml. Hoy no deja nada fuera: todo lo declarado es
# de agosto o antes.
HASTA = "2026-08"
ARCHIVOS_HASTA_AGOSTO = 134
FILAS_HASTA_AGOSTO = 987461


def escribir(base, ruta: str, contenido: str) -> str:
    destino = base / os.path.dirname(ruta)
    destino.mkdir(parents=True, exist_ok=True)
    (base / ruta).write_text(contenido, encoding="utf-8")
    return str(base / ruta)


def declarado(ruta: str, tienda: str) -> ArchivoDeclarado:
    return ArchivoDeclarado(ruta=ruta, tienda=tienda, anio_mes="2026-06")


@pytest.fixture
def disco(tmp_path):
    """Dos CSV declarados, una carpeta vacía y un artefacto del sistema."""
    escribir(tmp_path, RUTA_HEB, HEADER_V1 + FILA + FILA)
    escribir(tmp_path, RUTA_YZA, HEADER_V1)
    (tmp_path / "2026" / "10_octubre").mkdir(parents=True)
    (tmp_path / "2026" / "06_junio" / ".DS_Store").write_text("basura", encoding="utf-8")
    (tmp_path / "2026" / "06_junio" / "notas.txt").write_text("hola", encoding="utf-8")
    return tmp_path


DECLARADOS = [declarado(RUTA_HEB, "heb"), declarado(RUTA_YZA, "yza")]


# --- Qué entra y qué no -----------------------------------------------------


def test_solo_entran_los_csv(disco):
    assert rutas_en_disco(str(disco)) == {RUTA_HEB, RUTA_YZA}


def test_las_carpetas_vacias_no_aportan_nada(disco):
    resultado = descubrir(base=str(disco), declarados=DECLARADOS, hasta=HASTA)
    assert len(resultado.archivos) == 2
    assert resultado.faltantes == ()


def test_cada_archivo_trae_sus_seis_medidas(disco):
    heb = descubrir(base=str(disco), declarados=DECLARADOS, hasta=HASTA).archivos[0]

    assert isinstance(heb, ArchivoFuente)
    assert (heb.ruta, heb.tienda, heb.anio_mes) == (RUTA_HEB, "heb", "2026-06")
    assert heb.filas == 2
    assert heb.variante == "V1"
    assert heb.bytes == os.path.getsize(disco / RUTA_HEB)
    assert heb.md5 == md5_de_archivo(str(disco / RUTA_HEB))
    assert heb.declarado is DECLARADOS[0]


def test_el_archivo_solo_con_header_es_vacio_no_error(disco):
    yza = descubrir(base=str(disco), declarados=DECLARADOS, hasta=HASTA).archivos[1]
    assert yza.filas == 0
    assert yza.vacio is True
    assert yza.variante == "V1"


def test_el_md5_es_del_contenido(disco):
    antes = descubrir(base=str(disco), declarados=DECLARADOS, hasta=HASTA).archivos[0].md5
    escribir(disco, RUTA_HEB, HEADER_V1 + FILA)
    despues = descubrir(base=str(disco), declarados=DECLARADOS, hasta=HASTA).archivos[0].md5
    assert despues != antes


# --- El cruce con archivos.yml ----------------------------------------------


def test_un_csv_sin_declarar_detiene_el_comando_y_lo_nombra(disco):
    escribir(disco, "2026/06_junio/scraping_detalle_intruso.csv", HEADER_V1 + FILA)

    with pytest.raises(ErrorDescubrimiento) as e:
        descubrir(base=str(disco), declarados=DECLARADOS, hasta=HASTA)

    assert "2026/06_junio/scraping_detalle_intruso.csv" in str(e.value)


def test_un_declarado_que_no_existe_se_reporta_sin_abortar(disco):
    fantasma = declarado("2026/06_junio/scraping_detalle_gi.csv", "gi")
    resultado = descubrir(base=str(disco), declarados=[*DECLARADOS, fantasma], hasta=HASTA)

    assert resultado.faltantes == (fantasma.ruta,)
    assert [a.ruta for a in resultado.archivos] == [RUTA_HEB, RUTA_YZA]


def test_sin_directorio_de_datos_falla_nombrandolo(tmp_path):
    with pytest.raises(ErrorDescubrimiento, match="No existe el directorio"):
        descubrir(base=str(tmp_path / "no_existe"), declarados=DECLARADOS, hasta=HASTA)


# --- El histórico real ------------------------------------------------------


@pytest.fixture(scope="module")
def historico(datos_reales):
    """El histórico completo en disco."""
    return descubrir(hasta=HASTA)


@pytest.fixture(scope="module")
def hasta_agosto(datos_reales):
    """Lo que realmente se ingiere: el corte de `gcp.yml`."""
    return descubrir()


def test_descubre_los_134_archivos(historico):
    assert len(historico.archivos) == TOTAL_ARCHIVOS
    assert historico.faltantes == ()
    assert len({a.ruta for a in historico.archivos}) == TOTAL_ARCHIVOS


def test_todos_traen_sus_medidas(historico):
    for a in historico.archivos:
        assert len(a.md5) == 32
        assert a.bytes > 0
        assert a.variante in POR_VARIANTE
        assert a.tienda and a.anio_mes


def test_el_reparto_por_variante(historico):
    conteo = {}
    for a in historico.archivos:
        conteo[a.variante] = conteo.get(a.variante, 0) + 1
    assert conteo == POR_VARIANTE


def test_las_filas_cuadran_con_el_historico(historico):
    assert sum(a.filas for a in historico.archivos) == TOTAL_FILAS


@pytest.mark.skip(reason="septiembre pendiente de cierre: sin archivos vacíos en disco")
def test_los_dos_archivos_de_septiembre_estan_vacios(historico):
    vacios = {a.ruta for a in historico.archivos if a.vacio}
    assert vacios == {
        "2026/09_septiembre/scraping_detalle_benavides.csv",
        "2026/09_septiembre/scraping_detalles_fahorro.csv",
    }
    assert {a.bytes for a in historico.archivos if a.vacio} == {77}


def test_el_inventario_declarado_y_el_disco_son_el_mismo_conjunto(historico, declarados):
    assert {a.ruta for a in historico.archivos} == {d.ruta for d in declarados}


# --- El corte de mes --------------------------------------------------------


def test_por_defecto_solo_llega_hasta_el_mes_declarado(hasta_agosto):
    assert hasta_agosto.hasta == HASTA
    assert len(hasta_agosto.archivos) == ARCHIVOS_HASTA_AGOSTO
    assert max(a.anio_mes for a in hasta_agosto.archivos) == HASTA


@pytest.mark.skip(reason="septiembre pendiente de cierre: no hay mes posterior al corte declarado")
def test_septiembre_queda_fuera_de_rango_no_faltante(hasta_agosto):
    assert hasta_agosto.fuera_de_rango != ()
    assert hasta_agosto.faltantes == ()


def test_las_filas_del_corte(hasta_agosto):
    assert sum(a.filas for a in hasta_agosto.archivos) == FILAS_HASTA_AGOSTO


@pytest.mark.skip(reason="septiembre pendiente de cierre: no hay mes en curso declarado")
def test_el_mes_en_curso_solo_entra_si_se_pide_explicito(historico, hasta_agosto):
    """Reprocesar el mes abierto es una decisión, no un descuido."""
    assert len(historico.archivos) > len(hasta_agosto.archivos)
    assert historico.fuera_de_rango == ()


def test_un_archivo_fuera_de_rango_no_se_mide(disco):
    """No se le calcula MD5: el mes abierto todavía cambia bajo los pies."""
    resultado = descubrir(base=str(disco), declarados=DECLARADOS, hasta="2026-05")

    assert resultado.archivos == ()
    assert resultado.fuera_de_rango == (RUTA_HEB, RUTA_YZA)
    assert resultado.faltantes == ()


def test_un_intruso_fuera_del_corte_se_avisa_pero_no_aborta(disco):
    """El mes abierto se está escribiendo: no puede bloquear los meses cerrados."""
    escribir(disco, "2026/06_junio/scraping_detalle_intruso.csv", HEADER_V1 + FILA)

    resultado = descubrir(base=str(disco), declarados=DECLARADOS, hasta="2026-05")

    assert resultado.sin_declarar == ("2026/06_junio/scraping_detalle_intruso.csv",)
    assert resultado.archivos == ()


def test_un_intruso_dentro_del_corte_si_aborta(disco):
    escribir(disco, "2026/06_junio/scraping_detalle_intruso.csv", HEADER_V1 + FILA)

    with pytest.raises(ErrorDescubrimiento, match="intruso"):
        descubrir(base=str(disco), declarados=DECLARADOS, hasta="2026-06")
