"""Normalización de los campos crudos a los tipos de la capa bronce.

Cubre la fecha de captura, el precio y el SKU, y ensambla los flags de calidad
de cada fila. El armado del DataFrame de bronce llega en el issue siguiente.

Regla del módulo: normalizar nunca aborta el archivo. Un valor que no se puede
interpretar devuelve `None` junto con su bandera de fallo, y quien ensambla la
fila decide qué flag de calidad emitir. El valor original se conserva siempre
en la columna `_raw` correspondiente.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from precios_load.esquemas import Esquema

# Flag de calidad que corresponde a una fecha ilegible.
FLAG_FECHA_NO_PARSEABLE = "FECHA_NO_PARSEABLE"

# Los formatos literales presentes en el histórico, en cascada.
#
# Son los 6 de la tabla del inventario, escritos como 5 patrones: la hora sin
# cero a la izquierda (`06/03/26 2:32`, fahorro de marzo y heb de agosto) la
# cubre `%H` del cuarto patrón, que acepta uno o dos dígitos.
#
# Se prueban en este orden, sin inferencia. `%Y` exige exactamente 4 dígitos y
# `%y` exactamente 2, así que los patrones son mutuamente excluyentes y ningún
# valor puede caer en dos. El orden es solo por frecuencia en el histórico.
#
# Lo que esta cascada evita: `08/03/26` es el 8 de marzo. Un `pd.to_datetime`
# con inferencia libre lo leería como 3 de agosto y el error sería silencioso.
FORMATOS_FECHA = (
    "%d/%m/%y",           # 07/02/26          aurrera, walmart, guadalajara y ~15 más
    "%Y-%m-%d %H:%M:%S",  # 2025-12-09 18:37:43
    "%d/%m/%y %H:%M",     # 05/02/26 13:41    soriana feb, heb ago (incluye 2:32)
    "%d/%m/%Y %H:%M",     # 21/12/2025 21:45  farmalisto e isseg de dic-2025
    "%Y-%m-%d",           # 2026-02-05        benavides febrero
)


def parsear_fecha(valor: str) -> tuple[datetime | None, bool]:
    """Interpreta la fecha de captura probando los formatos conocidos en orden.

    Devuelve `(fecha, True)` con el primer formato que coincide, o
    `(None, False)` si el valor está vacío o no coincide con ninguno. Nunca
    lanza excepción: el archivo debe seguir procesándose.
    """
    if not isinstance(valor, str):
        return None, False

    texto = valor.strip()
    if not texto:
        return None, False

    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato), True
        except ValueError:
            continue

    return None, False


# ---------------------------------------------------------------------------
# Precio
# ---------------------------------------------------------------------------

# Flags de calidad del precio.
FLAG_PRECIO_NO_DISPONIBLE = "PRECIO_NO_DISPONIBLE"
FLAG_PRECIO_NO_PARSEABLE = "PRECIO_NO_PARSEABLE"
FLAG_PRECIO_CERO = "PRECIO_CERO"

# Centinelas de texto: el scraper no encontró precio. No son cero, son ausencia
# de dato, así que resuelven a NULL. Se comparan en mayúsculas y sin espacios,
# porque el mismo centinela aparece con distinta caja según la tienda.
CENTINELAS_PRECIO = frozenset(
    {
        "",              # fesa, fahorro, guadalajara, aurrera
        "NO DISPONIBLE",  # walmart, aurrera, farmalisto, fesa
        "N/A",           # guadalajara junio
        "NULL",          # guadalajara junio
        "#N/D",          # columna NDF de fahorro junio, si alguna vez se conserva
    }
)

# Forma que debe tener el valor una vez limpio, antes de convertirlo.
_NUMERO_LIMPIO = re.compile(r"\d+(\.\d+)?")


def parsear_precio(valor: str) -> tuple[Decimal | None, bool, list[str]]:
    """Interpreta un precio literal del histórico y sus flags de calidad.

    Devuelve `(precio, ok, flags)`. Un centinela o un valor ilegible dan
    `(None, False, [flag])`; un cero real da `(Decimal("0.00"), True,
    [PRECIO_CERO])`. Nunca lanza excepción.

    Reglas de separadores, deducidas de los 6 patrones del histórico:

    - `$` y espacios se descartan (`$1787.00`).
    - Los puntos finales sobrantes se recortan (`31.67..` de la comer).
    - Coma y punto juntos: la coma es millar (`$1,787.00` -> 1787.00).
    - Solo coma: 3 dígitos después es millar, 1 o 2 es decimal.
    - Dos o más puntos: los primeros son millar y el último decimal, así que
      `1.173.00` de fahorro es mil ciento setenta y tres, no 1.173.
    """
    if not isinstance(valor, str):
        return None, False, [FLAG_PRECIO_NO_PARSEABLE]

    texto = valor.strip()
    if texto.upper() in CENTINELAS_PRECIO:
        return None, False, [FLAG_PRECIO_NO_DISPONIBLE]

    limpio = _limpiar_precio(texto)
    if limpio is None or not _NUMERO_LIMPIO.fullmatch(limpio):
        return None, False, [FLAG_PRECIO_NO_PARSEABLE]

    try:
        precio = Decimal(limpio)
    except InvalidOperation:
        return None, False, [FLAG_PRECIO_NO_PARSEABLE]

    return precio, True, [FLAG_PRECIO_CERO] if precio == 0 else []


def _limpiar_precio(texto: str) -> str | None:
    """Quita moneda y separadores de millar. `None` si la forma es ambigua."""
    limpio = texto.replace("$", "").replace(" ", "").replace(" ", "")
    limpio = limpio.rstrip(".")

    if "," in limpio:
        if "." in limpio:
            # Coma y punto juntos: la coma solo puede ser el millar.
            limpio = limpio.replace(",", "")
        else:
            decimales = limpio.rsplit(",", 1)[1]
            if len(decimales) == 3:
                limpio = limpio.replace(",", "")
            elif len(decimales) in (1, 2):
                limpio = limpio.replace(",", ".")
            else:
                return None

    if limpio.count(".") > 1:
        # Todos los puntos menos el último son separador de millar.
        entero, decimales = limpio.rsplit(".", 1)
        limpio = entero.replace(".", "") + "." + decimales

    return limpio


# ---------------------------------------------------------------------------
# SKU
# ---------------------------------------------------------------------------

FLAG_SKU_CENTINELA = "SKU_CENTINELA"

# Centinelas de SKU. No son identificadores de producto: `search` es el
# marcador que deja el scraper de aurrera cuando cae en la página de búsqueda
# (855 filas en cada uno de sus 6 archivos) y `N/A` lo escriben fesa, gi, yza,
# klyns y soriana. Tratarlos como SKU genera duplicados falsos masivos: en
# `2026/07_julio/scraping_detalle_fesa.csv` un solo `N/A` aparece 485 veces.
CENTINELAS_SKU = frozenset({"", "SEARCH", "N/A"})


def parsear_sku(valor: str) -> tuple[str | None, bool]:
    """Devuelve `(sku, es_centinela)`. El literal se conserva en `sku_raw`.

    Un SKU legítimo pasa intacto salvo los espacios de los extremos. Un
    centinela devuelve `None` para que no se agrupe con nada.
    """
    if not isinstance(valor, str):
        return None, True

    texto = valor.strip()
    if texto.upper() in CENTINELAS_SKU:
        return None, True

    return texto, False


# ---------------------------------------------------------------------------
# Fila completa
# ---------------------------------------------------------------------------

FLAG_FILA_VACIA = "FILA_VACIA"


def es_fila_vacia(fila: list[str]) -> bool:
    """Una fila `,,,,,,,` del CSV: todas sus celdas vacías.

    Son 150 en el histórico (88 en guadalajara febrero, 61 en aurrera febrero,
    1 en chedraui febrero). No se descartan: bronce es 1:1 en filas con el CSV
    de origen para poder reconciliar conteos contra raw. Se marcan aquí y se
    filtran en silver.
    """
    return all(not celda.strip() for celda in fila)


@dataclass(frozen=True)
class FilaNormalizada:
    """Los campos tipados de una fila, con su literal y sus flags de calidad."""

    sku: str | None
    sku_raw: str
    precio_actual: Decimal | None
    precio_actual_raw: str
    precio_oferta: Decimal | None
    precio_oferta_raw: str
    fecha_captura: datetime | None
    fecha_captura_raw: str
    sku_es_centinela: bool
    precio_parse_ok: bool
    fecha_parse_ok: bool
    fila_vacia: bool
    calidad_flags: tuple[str, ...]


def normalizar_fila(esquema: Esquema, fila: list[str]) -> FilaNormalizada:
    """Normaliza una fila del CSV y acumula todos sus flags de calidad.

    `calidad_flags` lleva **todos** los flags aplicables, no el primero: una
    fila vacía sale con `FILA_VACIA`, `SKU_CENTINELA`, `PRECIO_NO_DISPONIBLE` y
    `FECHA_NO_PARSEABLE` a la vez.

    Los flags de precio no distinguen la columna porque son el mismo literal
    que emite `parsear_precio`; qué columna falló se lee en `precio_actual` y
    `precio_oferta`, que quedan en NULL.
    """
    sku_raw = esquema.valor(fila, "sku")
    actual_raw = esquema.valor(fila, "precio_actual")
    oferta_raw = esquema.valor(fila, "precio_oferta")
    fecha_raw = esquema.valor(fila, "fecha_captura")

    vacia = es_fila_vacia(fila)
    sku, es_centinela = parsear_sku(sku_raw)
    actual, actual_ok, flags_actual = parsear_precio(actual_raw)
    oferta, oferta_ok, flags_oferta = parsear_precio(oferta_raw)
    fecha, fecha_ok = parsear_fecha(fecha_raw)

    flags: list[str] = []
    if vacia:
        flags.append(FLAG_FILA_VACIA)
    if es_centinela:
        flags.append(FLAG_SKU_CENTINELA)
    flags.extend(flags_actual)
    flags.extend(flags_oferta)
    if not fecha_ok:
        flags.append(FLAG_FECHA_NO_PARSEABLE)

    return FilaNormalizada(
        sku=sku,
        sku_raw=sku_raw,
        precio_actual=actual,
        precio_actual_raw=actual_raw,
        precio_oferta=oferta,
        precio_oferta_raw=oferta_raw,
        fecha_captura=fecha,
        fecha_captura_raw=fecha_raw,
        sku_es_centinela=es_centinela,
        precio_parse_ok=actual_ok and oferta_ok,
        fecha_parse_ok=fecha_ok,
        fila_vacia=vacia,
        # dict.fromkeys deduplica sin perder el orden: si las dos columnas de
        # precio fallan igual, el flag aparece una sola vez.
        calidad_flags=tuple(dict.fromkeys(flags)),
    )
