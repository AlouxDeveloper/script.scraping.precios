"""Detección de la variante de header y mapeo a nombres canónicos.

Los 139 archivos del histórico traen 6 encabezados distintos. Un `read_csv`
ingenuo produciría columnas diferentes según el mes y el esquema de la tabla en
BigQuery sería inestable.

Dos decisiones que sostienen todo el módulo:

1. La **etiqueta** de la variante (V1..V6) se decide por la firma exacta del
   header, respetando mayúsculas. V2 y V6 solo se diferencian en eso, y saber
   de cuál viene una fila es linaje útil.
2. El **mapeo** de columnas se resuelve por nombre normalizado, así que un
   cambio de mayúsculas no rompe la lectura una vez identificada la variante.

Una firma desconocida detiene el proceso nombrando el archivo. Nunca se infiere
un esquema nuevo en silencio.
"""

import unicodedata
from dataclasses import dataclass

from precios_load.config import ArchivoDeclarado

# Nombres con los que viaja el dato de aquí en adelante.
CANONICAS = (
    "sku",
    "url_producto",
    "producto",
    "precio_actual",
    "precio_oferta",
    "url_imagen",
    "fecha_captura",
    "tienda",
)

# Cada nombre que aparece en el histórico, ya normalizado, y a qué corresponde.
# El campo de fecha tiene 3 nombres y el precio principal 2.
SINONIMOS = {
    "sku": "sku",
    "url_producto": "url_producto",
    "producto": "producto",
    "precio_actual": "precio_actual",
    "precio_normal": "precio_actual",
    "precio_oferta": "precio_oferta",
    "url_imagen": "url_imagen",
    "fecha_hora_captura": "fecha_captura",
    "fecha": "fecha_captura",
    "tienda": "tienda",
}

# Firmas exactas admitidas. La clave es el header tal cual aparece en el CSV.
VARIANTES = {
    "SKU,URL_PRODUCTO,Producto,Precio_Actual,Precio_Oferta,URL_IMAGEN,Fecha_Hora_Captura,Tienda": "V1",
    "SKU,URL_PRODUCTO,PRODUCTO,PRECIO_ACTUAL,PRECIO_OFERTA,URL_IMAGEN,FECHA,TIENDA": "V2",
    "SKU,URL_Producto,Producto,Precio_Normal,Precio_Oferta,URL_IMAGEN,Fecha_Hora_Captura,Tienda": "V3",
    "SKU,URL_PRODUCTO,PRODUCTO,PRECIO_ACTUAL,PRECIO_OFERTA,URL_IMAGEN,FECHA,TIENDA,NDF": "V5",
    "SKU,URL_PRODUCTO,Producto,Precio_Actual,Precio_Oferta,URL_IMAGEN,Fecha,Tienda": "V6",
}

# El archivo sin header no tiene firma que leer: sus columnas se declaran en
# archivos.yml y la etiqueta se fija aquí.
VARIANTE_SIN_HEADER = "V4"


class ErrorEsquema(Exception):
    """Header que no corresponde a ninguna variante conocida."""


@dataclass(frozen=True)
class Esquema:
    """Cómo leer un archivo concreto."""

    variante: str
    columnas_origen: tuple[str, ...]
    # canónica -> posición en la fila del CSV
    indices: dict[str, int]
    columnas_descartar: tuple[str, ...] = ()
    sin_header: bool = False

    def valor(self, fila: list[str], canonica: str) -> str:
        """Lee una columna canónica de una fila, tolerando filas cortas."""
        i = self.indices[canonica]
        return fila[i] if i < len(fila) else ""


def normalizar(nombre: str) -> str:
    """`Fecha_Hora_Captura` -> `fecha_hora_captura`; quita acentos y espacios."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c)
    )
    return sin_acentos.strip().lower().replace(" ", "_")


def firma(columnas) -> str:
    """Firma exacta de un header, tal como se compara contra VARIANTES."""
    return ",".join(c.strip() for c in columnas)


def detectar(
    declarado: ArchivoDeclarado,
    cabecera: list[str] | None,
    primera_fila: list[str] | None = None,
) -> Esquema:
    """Devuelve el esquema del archivo, o falla nombrándolo.

    `cabecera` es la primera línea ya parseada como CSV, o None cuando el
    archivo está declarado como `sin_header`.

    `primera_fila` solo se usa en el caso `sin_header`: sin encabezado que
    comparar, el ancho de la primera fila de datos es la única forma de
    detectar que las `columnas` declaradas ya no corresponden al archivo. Sin
    esa comprobación, una columna de más leería todas las filas corridas.
    """
    if declarado.sin_header:
        columnas = tuple(declarado.columnas)
        variante = VARIANTE_SIN_HEADER
        if primera_fila is not None and len(primera_fila) != len(columnas):
            raise ErrorEsquema(
                f"{declarado.ruta}: declara {len(columnas)} columnas pero su "
                f"primera fila trae {len(primera_fila)}"
            )
    else:
        if not cabecera:
            raise ErrorEsquema(f"{declarado.ruta}: el archivo no tiene encabezado ni está declarado como sin_header")
        columnas = tuple(c.strip() for c in cabecera)
        variante = VARIANTES.get(firma(columnas))
        if variante is None:
            raise ErrorEsquema(
                f"{declarado.ruta}: header desconocido, no coincide con ninguna "
                f"variante V1..V6.\n  firma encontrada: {firma(columnas)}"
            )

    descartar = {normalizar(c) for c in declarado.columnas_descartar}
    indices: dict[str, int] = {}

    for i, columna in enumerate(columnas):
        norma = normalizar(columna)
        if norma in descartar:
            continue
        canonica = SINONIMOS.get(norma)
        if canonica is None:
            raise ErrorEsquema(
                f"{declarado.ruta}: la columna '{columna}' no tiene equivalente "
                f"canónico ni está en columnas_descartar"
            )
        if canonica in indices:
            raise ErrorEsquema(
                f"{declarado.ruta}: la columna canónica '{canonica}' llega dos "
                f"veces (posiciones {indices[canonica]} y {i})"
            )
        indices[canonica] = i

    faltantes = [c for c in CANONICAS if c not in indices]
    if faltantes:
        raise ErrorEsquema(
            f"{declarado.ruta} ({variante}): faltan columnas: {', '.join(faltantes)}"
        )

    return Esquema(
        variante=variante,
        columnas_origen=columnas,
        indices=indices,
        columnas_descartar=tuple(declarado.columnas_descartar),
        sin_header=declarado.sin_header,
    )
