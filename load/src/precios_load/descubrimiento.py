"""Recorrido de `salida/data`, cruzado contra el inventario declarado.

Es el primer paso de cualquier comando: qué hay en disco, cuánto pesa, cuántas
filas trae y con qué variante de header. El MD5 del contenido es la base de la
idempotencia: si un archivo no cambió, no se reprocesa.

El cruce con `archivos.yml` es estricto en una dirección y tolerante en la
otra. Un CSV en disco sin declarar **detiene el comando**: ingerirlo con un
slug inventado ensuciaría la partición de una tienda para siempre. Un archivo
declarado que no está en disco solo se reporta como faltante, porque es lo
normal mientras una corrida mensual aún no ha terminado.

Por la misma razón el recorrido corta en `anio_mes_maximo` (`gcp.yml`): el mes
en curso se está escribiendo mientras se ingiere, así que sus archivos y sus
MD5 todavía cambian. Los meses que quedan fuera del corte se reportan aparte,
no se miden ni se ingieren, y un CSV sin declarar en uno de esos meses tampoco
detiene el comando: mientras el scraping del mes abierto va dejando archivos,
abortar por ellos bloquearía la ingesta de los meses que sí están cerrados.
"""

import csv
import os
from collections import Counter
from dataclasses import dataclass

from precios_load.bronce import md5_de_archivo
from precios_load.config import (
    ArchivoDeclarado,
    anio_mes_de_ruta,
    cargar_archivos,
    cargar_config,
)
from precios_load.esquemas import detectar
from precios_load.normalizacion import parsear_fecha

# Extensión de los archivos que se consideran datos. Todo lo demás que aparezca
# bajo `salida/data` (`.DS_Store`, los `Zone.Identifier` de WSL, notas sueltas)
# se ignora sin comentarios.
EXTENSION = ".csv"


class ErrorDescubrimiento(Exception):
    """Hay datos en disco que el inventario no explica."""


@dataclass(frozen=True)
class ArchivoFuente:
    """Un CSV del histórico, ya medido y cruzado con su declaración."""

    ruta: str
    tienda: str
    anio_mes: str
    bytes: int
    md5: str
    filas: int
    variante: str
    declarado: ArchivoDeclarado
    # Mes mayoritario de las fechas internas y cuántas filas no caen en el mes
    # de la carpeta. Salen del mismo recorrido que cuenta las filas.
    anio_mes_dato: str | None = None
    filas_desfasadas: int = 0

    @property
    def desfase(self) -> bool:
        """Alguna fila trae una fecha de un mes distinto al de su carpeta."""
        return self.filas_desfasadas > 0

    @property
    def vacio(self) -> bool:
        """Solo header y cero filas: los dos archivos de 77 bytes de septiembre."""
        return self.filas == 0

    @property
    def nombre(self) -> str:
        return os.path.basename(self.ruta)


@dataclass(frozen=True)
class Descubrimiento:
    """Lo que se encontró, lo que faltó y lo que quedó fuera del corte de mes."""

    archivos: tuple[ArchivoFuente, ...]
    faltantes: tuple[str, ...]
    fuera_de_rango: tuple[str, ...] = ()
    hasta: str | None = None
    # CSV en disco sin declarar, pero de un mes posterior al corte: se avisa,
    # no se aborta. Dentro del corte, un intruso detiene el comando.
    sin_declarar: tuple[str, ...] = ()


def descubrir(
    base: str | None = None,
    declarados: list[ArchivoDeclarado] | None = None,
    hasta: str | None = None,
) -> Descubrimiento:
    """Mide cada archivo declarado que exista en disco y entre en el corte.

    `hasta` es el último `anio_mes` que se ingiere, inclusive; por defecto, el
    `anio_mes_maximo` de `gcp.yml`. Pasar un mes posterior amplía el corte, así
    que reprocesar el mes en curso es explícito y no un descuido.

    Falla si aparece un CSV sin declarar. Los declarados que no existan se
    devuelven en `faltantes` sin interrumpir el resto.
    """
    config = cargar_config() if base is None or hasta is None else None
    base = base if base is not None else config.ruta_datos()
    hasta = hasta if hasta is not None else config.anio_mes_maximo
    declarados = declarados if declarados is not None else cargar_archivos()

    if not os.path.isdir(base):
        raise ErrorDescubrimiento(f"No existe el directorio de datos: {base}")

    en_disco = rutas_en_disco(base)
    por_ruta = {d.ruta: d for d in declarados}

    sin_declarar = sorted(en_disco - set(por_ruta))
    dentro_del_corte = [r for r in sin_declarar if anio_mes_de_ruta(r) <= hasta]
    if dentro_del_corte:
        raise ErrorDescubrimiento(
            f"{len(dentro_del_corte)} archivo(s) en disco sin declarar en archivos.yml:\n  "
            + "\n  ".join(dentro_del_corte)
            + "\nDeclara cada uno con su tienda antes de ingerir."
        )

    archivos = []
    faltantes = []
    fuera_de_rango = []
    for d in declarados:
        if d.anio_mes > hasta:
            fuera_de_rango.append(d.ruta)
        elif d.ruta in en_disco:
            archivos.append(medir(d, base))
        else:
            faltantes.append(d.ruta)

    return Descubrimiento(
        archivos=tuple(archivos),
        faltantes=tuple(faltantes),
        fuera_de_rango=tuple(fuera_de_rango),
        hasta=hasta,
        sin_declarar=tuple(r for r in sin_declarar if r not in dentro_del_corte),
    )


def rutas_en_disco(base: str) -> set[str]:
    """Los CSV bajo `base`, como rutas relativas con `/`.

    Las carpetas vacías (`10_octubre` en adelante) no aportan nada y los
    archivos ocultos se ignoran.
    """
    encontradas = set()
    for carpeta, _, nombres in os.walk(base):
        for nombre in nombres:
            if nombre.startswith(".") or not nombre.lower().endswith(EXTENSION):
                continue
            ruta = os.path.join(carpeta, nombre)
            encontradas.add(os.path.relpath(ruta, base).replace(os.sep, "/"))
    return encontradas


def medir(declarado: ArchivoDeclarado, base: str) -> ArchivoFuente:
    """Tamaño, MD5, filas y variante de un archivo concreto."""
    ruta_csv = os.path.join(base, declarado.ruta)
    filas, variante, meses = _medidas_del_contenido(declarado, ruta_csv)
    desfasadas = sum(n for mes, n in meses.items() if mes != declarado.anio_mes)

    return ArchivoFuente(
        ruta=declarado.ruta,
        tienda=declarado.tienda,
        anio_mes=declarado.anio_mes,
        bytes=os.path.getsize(ruta_csv),
        md5=md5_de_archivo(ruta_csv),
        filas=filas,
        variante=variante,
        declarado=declarado,
        anio_mes_dato=(meses.most_common(1)[0][0] if meses else None),
        filas_desfasadas=desfasadas,
    )


def _medidas_del_contenido(
    declarado: ArchivoDeclarado, ruta_csv: str
) -> tuple[int, str, Counter]:
    """Filas, variante de header y meses de las fechas, en una sola lectura.

    Las filas se cuentan con `csv.reader`, no por saltos de línea: un nombre de
    producto con salto embebido es una sola fila, y este conteo tiene que
    cuadrar con el DataFrame de bronce para reconciliar contra raw.

    Los meses se cuentan aquí y no en un segundo recorrido porque el archivo ya
    está abierto: es lo que permite que `plan` avise de un desfase de mes sin
    ensamblar el DataFrame completo.
    """
    meses: Counter = Counter()
    with open(ruta_csv, encoding="utf-8", errors="replace", newline="") as f:
        lector = csv.reader(f)
        cabecera = None if declarado.sin_header else next(lector, None)
        primera = next(lector, None) if declarado.sin_header else None
        esquema = detectar(declarado, cabecera, primera_fila=primera)

        filas = 0
        for fila in [primera] if primera is not None else []:
            filas += 1
            fecha, ok = parsear_fecha(esquema.valor(fila, "fecha_captura"))
            if ok:
                meses[f"{fecha.year:04d}-{fecha.month:02d}"] += 1

        for fila in lector:
            filas += 1
            fecha, ok = parsear_fecha(esquema.valor(fila, "fecha_captura"))
            if ok:
                meses[f"{fecha.year:04d}-{fecha.month:02d}"] += 1

    return filas, esquema.variante, meses
