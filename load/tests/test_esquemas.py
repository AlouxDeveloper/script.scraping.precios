"""Las 6 variantes de header del histórico, con sus firmas literales."""

import csv
import os

import pytest

from precios_load.config import ArchivoDeclarado, cargar_archivos, cargar_config
from precios_load.esquemas import (
    CANONICAS,
    ErrorEsquema,
    Esquema,
    detectar,
    firma,
    normalizar,
)

# Firmas tal como aparecen en los archivos.
V1 = "SKU,URL_PRODUCTO,Producto,Precio_Actual,Precio_Oferta,URL_IMAGEN,Fecha_Hora_Captura,Tienda"
V2 = "SKU,URL_PRODUCTO,PRODUCTO,PRECIO_ACTUAL,PRECIO_OFERTA,URL_IMAGEN,FECHA,TIENDA"
V3 = "SKU,URL_Producto,Producto,Precio_Normal,Precio_Oferta,URL_IMAGEN,Fecha_Hora_Captura,Tienda"
V5 = "SKU,URL_PRODUCTO,PRODUCTO,PRECIO_ACTUAL,PRECIO_OFERTA,URL_IMAGEN,FECHA,TIENDA,NDF"
V6 = "SKU,URL_PRODUCTO,Producto,Precio_Actual,Precio_Oferta,URL_IMAGEN,Fecha,Tienda"

COLUMNAS_V4 = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta",
    "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda",
]

# Reparto esperado del histórico completo.
POR_VARIANTE = {"V1": 91, "V2": 30, "V3": 15, "V4": 1, "V5": 1, "V6": 1}


def declarado(ruta="2026/03_marzo/x.csv", **extra):
    base = {"ruta": ruta, "tienda": "x", "anio_mes": "2026-03"}
    return ArchivoDeclarado(**{**base, **extra})


def esquema_de(cabecera: str, **extra) -> Esquema:
    return detectar(declarado(**extra), cabecera.split(","))


# --- Normalización de nombres ----------------------------------------------


def test_normalizar():
    assert normalizar("Fecha_Hora_Captura") == "fecha_hora_captura"
    assert normalizar("URL_PRODUCTO") == "url_producto"
    assert normalizar("  Precio Normal  ") == "precio_normal"
    assert normalizar("Categoría") == "categoria"


# --- Las 6 variantes --------------------------------------------------------


@pytest.mark.parametrize("cabecera,etiqueta", [(V1, "V1"), (V2, "V2"), (V3, "V3"), (V6, "V6")])
def test_variantes_con_8_columnas(cabecera, etiqueta):
    e = esquema_de(cabecera)
    assert e.variante == etiqueta
    assert sorted(e.indices) == sorted(CANONICAS)
    assert e.indices["fecha_captura"] == 6
    assert e.indices["precio_actual"] == 3


def test_v3_mapea_precio_normal_a_precio_actual():
    e = esquema_de(V3)
    assert e.columnas_origen[3] == "Precio_Normal"
    assert e.indices["precio_actual"] == 3


def test_v5_descarta_la_columna_ndf():
    e = esquema_de(V5, columnas_descartar=("NDF",))
    assert e.variante == "V5"
    assert len(e.columnas_origen) == 9
    assert sorted(e.indices) == sorted(CANONICAS)
    assert 8 not in e.indices.values()


def test_v5_sin_declarar_el_descarte_falla():
    """Sin `columnas_descartar`, NDF no tiene canónica y debe detener el proceso."""
    with pytest.raises(ErrorEsquema, match="NDF"):
        esquema_de(V5)


def test_v4_sin_header_toma_las_columnas_declaradas():
    d = declarado(
        ruta="2026/06_junio/scraping_detalle_heb.csv",
        sin_header=True,
        columnas=tuple(COLUMNAS_V4),
    )
    e = detectar(d, None)

    assert e.variante == "V4"
    assert e.sin_header
    assert sorted(e.indices) == sorted(CANONICAS)


def test_v4_lee_la_primera_linea_como_dato():
    """La primera línea física de heb junio es el producto 900437."""
    d = declarado(sin_header=True, columnas=tuple(COLUMNAS_V4))
    e = detectar(d, None)
    fila = [
        "900437",
        "https://www.heb.com.mx/heb-cubrebocas-infantil-blanco-10-piezas-10-pz-900437/p",
        "Cubrebocas Infantil Blanco 10 Piezas 10 pz",
        "41.90",
        "41.90",
        "https://hebmx.vtexassets.com/arquivos/ids/835250-800-800",
        "2026-06-14 20:31:07",
        "HEB",
    ]
    assert e.valor(fila, "sku") == "900437"
    assert e.valor(fila, "precio_actual") == "41.90"
    assert e.valor(fila, "tienda") == "HEB"


# --- Una firma desconocida detiene el proceso -------------------------------


def test_header_desconocido_nombra_el_archivo_y_la_firma():
    with pytest.raises(ErrorEsquema) as e:
        esquema_de("SKU,URL,Nombre,Precio", ruta="2026/10_octubre/nuevo.csv")

    assert "2026/10_octubre/nuevo.csv" in str(e.value)
    assert "SKU,URL,Nombre,Precio" in str(e.value)


def test_solo_cambiar_mayusculas_ya_es_desconocido():
    """La etiqueta se decide por firma exacta: V2 y V6 solo difieren en eso."""
    with pytest.raises(ErrorEsquema, match="header desconocido"):
        esquema_de(V1.replace("Fecha_Hora_Captura", "FECHA_HORA_CAPTURA"))


def test_columna_repetida_falla():
    d = declarado(sin_header=True, columnas=tuple(COLUMNAS_V4) + ("Fecha",))
    with pytest.raises(ErrorEsquema, match="dos veces"):
        detectar(d, None)


def test_columna_faltante_falla():
    d = declarado(sin_header=True, columnas=tuple(COLUMNAS_V4[:-1]))
    with pytest.raises(ErrorEsquema, match="faltan columnas: tienda"):
        detectar(d, None)


def test_fila_mas_corta_que_el_header_no_revienta():
    e = esquema_de(V1)
    assert e.valor(["123", "url"], "tienda") == ""


def test_v4_con_un_ancho_distinto_al_declarado_falla():
    """Sin header no hay firma que comparar: el ancho es la única defensa."""
    d = declarado(sin_header=True, columnas=tuple(COLUMNAS_V4))

    with pytest.raises(ErrorEsquema, match="declara 8 columnas pero su primera fila trae 9"):
        detectar(d, None, primera_fila=["x"] * 9)


def test_v4_con_el_ancho_correcto_pasa():
    d = declarado(sin_header=True, columnas=tuple(COLUMNAS_V4))
    assert detectar(d, None, primera_fila=["x"] * 8).variante == "V4"


# --- El histórico completo --------------------------------------------------


def test_las_139_firmas_se_clasifican(tmp_path):
    base = cargar_config().ruta_datos()
    if not os.path.isdir(base):
        pytest.skip("salida/data no existe en esta máquina")

    conteo: dict[str, int] = {}
    for d in cargar_archivos():
        with open(os.path.join(base, d.ruta), encoding="utf-8", errors="replace", newline="") as f:
            cabecera = next(csv.reader(f), None)
        e = detectar(d, None if d.sin_header else cabecera)
        conteo[e.variante] = conteo.get(e.variante, 0) + 1

    assert conteo == POR_VARIANTE


def test_firma_recorta_espacios():
    assert firma([" SKU ", "Tienda "]) == "SKU,Tienda"
