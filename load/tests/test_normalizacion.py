"""Los 6 formatos de fecha del histórico, con sus valores literales."""

from decimal import Decimal

import pytest

from precios_load.config import ArchivoDeclarado
from tests.conftest import columna, esquema_y_filas
from precios_load.normalizacion import (
    FLAG_FECHA_NO_PARSEABLE,
    FLAG_PRECIO_CERO,
    FLAG_PRECIO_NO_DISPONIBLE,
    FLAG_PRECIO_NO_PARSEABLE,
    FLAG_FILA_VACIA,
    FLAG_SKU_CENTINELA,
    es_fila_vacia,
    normalizar_fila,
    parsear_fecha,
    parsear_precio,
    parsear_sku,
)

# Un valor real de cada formato de la tabla del inventario, con lo que debe
# significar: (valor, año, mes, día, hora, minuto, segundo).
FORMATOS = [
    ("2025-12-09 18:37:43", 2025, 12, 9, 18, 37, 43),  # la mayoría
    ("2026-02-05", 2026, 2, 5, 0, 0, 0),               # benavides febrero
    ("21/12/2025 21:45", 2025, 12, 21, 21, 45, 0),     # farmalisto e isseg dic-2025
    ("05/02/26 13:41", 2026, 2, 5, 13, 41, 0),         # soriana febrero, heb agosto
    ("06/03/26 2:32", 2026, 3, 6, 2, 32, 0),           # hora sin cero: fahorro marzo
    ("07/02/26", 2026, 2, 7, 0, 0, 0),                 # aurrera, walmart, guadalajara
]

# Los dos archivos que mezclan hora con y sin cero a la izquierda, con el
# reparto real de cada uno.
MIXTOS = {
    "2026/03_marzo/scraping_detalles_fahorro.csv": (9987, 1784),
    "2026/08_agosto/scraping_detalle_heb.csv": (4254, 2937),
}

# Reparto del histórico en disco: 150 fechas vacías, el resto parsea.
TOTAL_OK = 987311
TOTAL_FALLO = 150


# --- Los 6 formatos ---------------------------------------------------------


@pytest.mark.parametrize("valor,anio,mes,dia,hora,minuto,segundo", FORMATOS)
def test_los_6_formatos_parsean(valor, anio, mes, dia, hora, minuto, segundo):
    fecha, ok = parsear_fecha(valor)
    assert ok
    assert (fecha.year, fecha.month, fecha.day) == (anio, mes, dia)
    assert (fecha.hour, fecha.minute, fecha.second) == (hora, minuto, segundo)


def test_dia_primero_nunca_se_lee_como_mes():
    """El riesgo que justifica la cascada: `08/03/26` es el 8 de marzo."""
    fecha, ok = parsear_fecha("08/03/26")
    assert ok
    assert (fecha.day, fecha.month) == (8, 3)
    assert fecha.month != 8


def test_el_dia_13_confirma_el_orden():
    """13 no puede ser mes, así que fija el orden sin depender de la cascada."""
    fecha, _ = parsear_fecha("13/01/26")
    assert (fecha.day, fecha.month, fecha.year) == (13, 1, 2026)


def test_ano_de_dos_digitos_es_del_siglo_actual():
    fecha, _ = parsear_fecha("31/12/25")
    assert fecha.year == 2025


def test_el_formato_de_4_digitos_no_se_confunde_con_el_de_2():
    """`21/12/2025 21:45` es de 2025, nunca del año 20 ni del 25."""
    fecha, _ = parsear_fecha("21/12/2025 21:45")
    assert fecha.year == 2025


# --- Valores que no parsean -------------------------------------------------


@pytest.mark.parametrize(
    "valor",
    ["", "   ", "sin fecha", "2026-13-45", "05-02-2026", "1738771200", None, 20260205],
)
def test_valor_no_parseable_devuelve_none_sin_excepcion(valor):
    fecha, ok = parsear_fecha(valor)
    assert fecha is None
    assert ok is False


def test_el_flag_de_calidad_esta_declarado():
    assert FLAG_FECHA_NO_PARSEABLE == "FECHA_NO_PARSEABLE"


def test_los_espacios_alrededor_no_estorban():
    fecha, ok = parsear_fecha("  2026-02-05 18:37:43\n")
    assert ok
    assert (fecha.day, fecha.hour) == (5, 18)


# --- Los archivos que mezclan dos formatos ----------------------------------


@pytest.mark.parametrize("ruta,esperado", sorted(MIXTOS.items()))
def test_archivos_con_hora_mixta_parsean_entero(ruta, esperado, datos_reales, por_ruta):
    total_esperado, sin_cero_esperado = esperado

    total = sin_cero = 0
    for valor in columna(datos_reales, por_ruta[ruta], "fecha_captura"):
        _, ok = parsear_fecha(valor)
        assert ok, f"{ruta}: no parseó {valor!r}"
        total += 1
        if len(valor.strip().split(" ")[1].split(":")[0]) == 1:
            sin_cero += 1

    assert (total, sin_cero) == (total_esperado, sin_cero_esperado)


# --- El histórico completo --------------------------------------------------


def test_todo_el_historico_parsea_salvo_las_fechas_vacias(datos_reales, declarados):
    ok = fallo = 0
    for d in declarados:
        for valor in columna(datos_reales, d, "fecha_captura"):
            _, exito = parsear_fecha(valor)
            if exito:
                ok += 1
            else:
                fallo += 1
                assert valor.strip() == "", f"{d.ruta}: no parseó {valor!r}"

    assert (ok, fallo) == (TOTAL_OK, TOTAL_FALLO)


# ===========================================================================
# Precio
# ===========================================================================

# Un valor real de cada patrón de la tabla del inventario.
PATRONES_PRECIO = [
    ("41.90", "41.90"),        # decimal plano, la mayoría
    ("$1787.00", "1787.00"),   # con $, fesa casi todos los meses
    ("$1,787.00", "1787.00"),  # con $ y coma de millar, fesa mayo
    ("9,999.99", "9999.99"),   # coma de millar sin $, benavides e isseg
    ("1.173.00", "1173.00"),   # punto como millar, fahorro feb y mar
    ("31.67..", "31.67"),      # doble punto final, la comer mar-ago
]

# Centinelas de texto: ausencia de dato, no cero.
CENTINELAS = ["No disponible", "NO DISPONIBLE", "", "   ", "#N/D", "N/A", "null"]

# Reparto del histórico en disco sobre las dos columnas de precio
# (septiembre pendiente de cierre).
PRECIO_TOTAL_OK = 1928507
PRECIO_TOTAL_NULO = 46415
PRECIO_TOTAL_CERO = 12402


# --- Los 6 patrones ---------------------------------------------------------


@pytest.mark.parametrize("valor,esperado", PATRONES_PRECIO)
def test_los_6_patrones_de_precio(valor, esperado):
    precio, ok, flags = parsear_precio(valor)
    assert ok
    assert precio == Decimal(esperado)
    assert flags == []


def test_el_punto_de_millar_no_se_lee_como_decimal():
    """El riesgo de fahorro: `1.173.00` es mil ciento setenta y tres."""
    precio, ok, _ = parsear_precio("1.173.00")
    assert ok
    assert precio == Decimal("1173.00")
    assert precio != Decimal("1.173")


def test_los_puntos_finales_sobrantes_se_recortan():
    """La comer escribe `31.67..` y, 20 veces, `160.00.`."""
    assert parsear_precio("31.67..")[0] == Decimal("31.67")
    assert parsear_precio("160.00.")[0] == Decimal("160.00")


def test_conserva_los_decimales_del_literal():
    assert str(parsear_precio("41.90")[0]) == "41.90"


def test_precio_entero_sin_decimales():
    precio, ok, flags = parsear_precio("376")
    assert (precio, ok, flags) == (Decimal("376"), True, [])


# --- Coma: millar o decimal según los dígitos que la siguen -----------------


def test_coma_con_3_digitos_es_millar():
    assert parsear_precio("1,118")[0] == Decimal("1118")


@pytest.mark.parametrize("valor,esperado", [("9,99", "9.99"), ("9,9", "9.9")])
def test_coma_con_1_o_2_digitos_es_decimal(valor, esperado):
    assert parsear_precio(valor)[0] == Decimal(esperado)


def test_coma_con_punto_siempre_es_millar():
    assert parsear_precio("1,118.00")[0] == Decimal("1118.00")


# --- Centinelas: ausencia de dato, nunca cero -------------------------------


@pytest.mark.parametrize("valor", CENTINELAS)
def test_centinelas_dan_null_con_flag(valor):
    precio, ok, flags = parsear_precio(valor)
    assert precio is None
    assert ok is False
    assert flags == [FLAG_PRECIO_NO_DISPONIBLE]


def test_el_cero_es_un_valor_real_distinguible_del_faltante():
    cero, ok, flags = parsear_precio("0.00")
    assert ok is True
    assert cero == Decimal("0.00")
    assert flags == [FLAG_PRECIO_CERO]

    faltante, ok_faltante, flags_faltante = parsear_precio("No disponible")
    assert faltante is None and ok_faltante is False
    assert flags_faltante != flags


def test_el_cero_sin_decimales_tambien_lleva_flag():
    precio, ok, flags = parsear_precio("0")
    assert (precio, ok, flags) == (Decimal("0"), True, [FLAG_PRECIO_CERO])


# --- Basura: ni valor ni centinela conocido ---------------------------------


@pytest.mark.parametrize("valor", ["abc", "1,2345", "$", "12.34.56.78x", None, 41.9])
def test_valor_ilegible_no_revienta(valor):
    precio, ok, flags = parsear_precio(valor)
    assert precio is None
    assert ok is False
    assert flags == [FLAG_PRECIO_NO_PARSEABLE]


# --- El histórico completo --------------------------------------------------


def test_todo_el_historico_de_precios_parsea_o_es_centinela(datos_reales, declarados):
    ok = nulo = cero = 0
    for d in declarados:
        for valor in columna(datos_reales, d, "precio_actual", "precio_oferta"):
            _, exito, flags = parsear_precio(valor)
            if exito:
                ok += 1
                cero += FLAG_PRECIO_CERO in flags
            else:
                nulo += 1
                assert flags == [FLAG_PRECIO_NO_DISPONIBLE], f"{d.ruta}: {valor!r}"

    assert (ok, nulo, cero) == (PRECIO_TOTAL_OK, PRECIO_TOTAL_NULO, PRECIO_TOTAL_CERO)


# ===========================================================================
# SKU y flags por fila
# ===========================================================================

# Header V1 y una fila legítima de heb, base de las variaciones de los tests.
COLUMNAS_V1 = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta",
    "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda",
]
FILA_BUENA = [
    "900437",
    "https://www.heb.com.mx/heb-cubrebocas-900437/p",
    "Cubrebocas Infantil Blanco 10 Piezas 10 pz",
    "41.90",
    "41.90",
    "https://hebmx.vtexassets.com/arquivos/ids/835250-800-800",
    "2026-06-14 20:31:07",
    "HEB",
]

# Reparto del histórico en disco por fila (septiembre pendiente de cierre).
FILAS_TOTAL = 987461
FILAS_SKU_CENTINELA = 7280  # search 5130 + N/A 1564 + vacío 586
FILAS_VACIAS = 150
FILAS_SIN_FLAGS = 952751

# Cada centinela de SKU con las veces que aparece en el histórico.
CENTINELAS_SKU_LITERALES = {"search": 5130, "N/A": 1564, "": 586}


def esquema_v1():
    from precios_load.esquemas import detectar

    return detectar(
        ArchivoDeclarado(ruta="2026/06_junio/x.csv", tienda="heb", anio_mes="2026-06"),
        COLUMNAS_V1,
    )


def fila_con(**cambios) -> list[str]:
    """La fila legítima con algunas celdas sustituidas, por nombre canónico."""
    posiciones = {
        canonica: i
        for i, canonica in enumerate(
            ["sku", "url_producto", "producto", "precio_actual", "precio_oferta",
             "url_imagen", "fecha_captura", "tienda"]
        )
    }
    fila = list(FILA_BUENA)
    for canonica, valor in cambios.items():
        fila[posiciones[canonica]] = valor
    return fila


def normalizada(**cambios):
    return normalizar_fila(esquema_v1(), fila_con(**cambios))


# --- parsear_sku ------------------------------------------------------------


@pytest.mark.parametrize("valor", sorted(CENTINELAS_SKU_LITERALES))
def test_los_centinelas_de_sku_dan_null(valor):
    sku, es_centinela = parsear_sku(valor)
    assert sku is None
    assert es_centinela is True


def test_el_centinela_no_depende_de_la_caja():
    assert parsear_sku("SEARCH")[0] is None
    assert parsear_sku("n/a")[0] is None


@pytest.mark.parametrize("valor", ["900437", "7501234567890", "ABC-123", "0"])
def test_un_sku_legitimo_pasa_intacto(valor):
    sku, es_centinela = parsear_sku(valor)
    assert sku == valor
    assert es_centinela is False


def test_el_sku_se_recorta_pero_no_se_altera():
    assert parsear_sku("  900437  ") == ("900437", False)


def test_sku_no_texto_es_centinela():
    assert parsear_sku(None) == (None, True)


# --- Fila vacía -------------------------------------------------------------


def test_detecta_la_fila_vacia_del_historico():
    """La fila literal `,,,,,,,` de guadalajara y aurrera de febrero."""
    assert es_fila_vacia(["", "", "", "", "", "", "", ""]) is True
    assert es_fila_vacia(["", "   ", "\t"]) is True
    assert es_fila_vacia(FILA_BUENA) is False


def test_la_fila_vacia_se_marca_y_no_se_descarta():
    n = normalizar_fila(esquema_v1(), ["", "", "", "", "", "", "", ""])

    assert n.fila_vacia is True
    assert n.sku is None and n.precio_actual is None and n.fecha_captura is None
    # El literal siempre se conserva, aunque esté vacío.
    assert n.sku_raw == "" and n.precio_actual_raw == "" and n.fecha_captura_raw == ""


# --- calidad_flags acumula todo lo aplicable --------------------------------


def test_una_fila_sana_no_lleva_flags():
    n = normalizada()
    assert n.calidad_flags == ()
    assert n.sku == "900437"
    assert n.precio_actual == Decimal("41.90")
    assert n.fecha_captura.year == 2026
    assert n.precio_parse_ok and n.fecha_parse_ok


def test_la_fila_vacia_acumula_los_cuatro_flags():
    n = normalizar_fila(esquema_v1(), ["", "", "", "", "", "", "", ""])
    assert n.calidad_flags == (
        FLAG_FILA_VACIA,
        FLAG_SKU_CENTINELA,
        FLAG_PRECIO_NO_DISPONIBLE,
        FLAG_FECHA_NO_PARSEABLE,
    )


def test_acumula_flags_de_campos_distintos():
    n = normalizada(sku="search", precio_oferta="0.00", fecha_captura="sin fecha")
    assert n.calidad_flags == (
        FLAG_SKU_CENTINELA,
        FLAG_PRECIO_CERO,
        FLAG_FECHA_NO_PARSEABLE,
    )
    assert n.sku_es_centinela is True
    assert n.precio_actual == Decimal("41.90")
    assert n.precio_oferta == Decimal("0.00")
    assert n.fecha_captura is None


def test_el_mismo_flag_en_las_dos_columnas_de_precio_no_se_repite():
    n = normalizada(precio_actual="No disponible", precio_oferta="")
    assert n.calidad_flags == (FLAG_PRECIO_NO_DISPONIBLE,)
    assert n.precio_actual is None and n.precio_oferta is None
    assert n.precio_parse_ok is False


def test_precio_parse_ok_es_falso_si_falla_cualquiera_de_las_dos():
    assert normalizada(precio_oferta="No disponible").precio_parse_ok is False
    assert normalizada(precio_actual="No disponible").precio_parse_ok is False


def test_los_literales_originales_se_conservan():
    n = normalizada(sku="N/A", precio_actual="$1,787.00", precio_oferta="31.67..")
    assert n.sku_raw == "N/A"
    assert n.precio_actual_raw == "$1,787.00"
    assert n.precio_oferta_raw == "31.67.."
    assert n.precio_actual == Decimal("1787.00")


# --- El histórico completo --------------------------------------------------


def test_el_reparto_de_flags_del_historico(datos_reales, declarados):
    filas = centinelas = vacias = sin_flags = 0

    for d in declarados:
        esquema, todas = esquema_y_filas(datos_reales, d)
        for fila in todas:
            n = normalizar_fila(esquema, fila)
            filas += 1
            centinelas += n.sku_es_centinela
            sin_flags += not n.calidad_flags
            if n.fila_vacia:
                vacias += 1
                # Ninguna se descarta y todas llevan los cuatro flags.
                assert n.calidad_flags == (
                    FLAG_FILA_VACIA,
                    FLAG_SKU_CENTINELA,
                    FLAG_PRECIO_NO_DISPONIBLE,
                    FLAG_FECHA_NO_PARSEABLE,
                )

    assert filas == FILAS_TOTAL
    assert (centinelas, vacias, sin_flags) == (
        FILAS_SKU_CENTINELA, FILAS_VACIAS, FILAS_SIN_FLAGS,
    )


def test_los_centinelas_de_sku_del_historico_estan_contados(datos_reales, declarados):
    conteo = {valor: 0 for valor in CENTINELAS_SKU_LITERALES}

    for d in declarados:
        for valor in columna(datos_reales, d, "sku"):
            if valor.strip() in conteo:
                conteo[valor.strip()] += 1

    assert conteo == CENTINELAS_SKU_LITERALES
