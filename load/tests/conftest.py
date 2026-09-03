"""Fixtures y ayudas compartidas por los tests que tocan el histórico real.

`salida/` está en `.gitignore`: si no existe localmente, los tests que
dependen de él se saltan en vez de fallar.
"""

import csv
import os

import pytest

from precios_load.config import ArchivoDeclarado, cargar_archivos, cargar_config
from precios_load.esquemas import Esquema, detectar


@pytest.fixture(scope="session")
def datos_reales() -> str:
    """Ruta a `salida/data`, o salta el test si no está en esta máquina."""
    base = cargar_config().ruta_datos()
    if not os.path.isdir(base):
        pytest.skip("salida/data no existe en esta máquina")
    return base


@pytest.fixture(scope="session")
def declarados() -> list[ArchivoDeclarado]:
    """El inventario de `archivos.yml`, leído una sola vez por sesión."""
    return cargar_archivos()


@pytest.fixture(scope="session")
def por_ruta(declarados) -> dict[str, ArchivoDeclarado]:
    """El inventario indexado por ruta."""
    return {d.ruta: d for d in declarados}


def esquema_y_filas(base: str, declarado: ArchivoDeclarado) -> tuple[Esquema, list[list[str]]]:
    """Abre un CSV real y devuelve su esquema y sus filas de datos.

    Los archivos declarados `sin_header` no gastan la primera línea: ya es dato.
    """
    ruta = os.path.join(base, declarado.ruta)
    with open(ruta, encoding="utf-8", errors="replace", newline="") as f:
        lector = csv.reader(f)
        cabecera = None if declarado.sin_header else next(lector, None)
        return detectar(declarado, cabecera), list(lector)


def columna(base: str, declarado: ArchivoDeclarado, *canonicas: str):
    """Los valores de una o más columnas canónicas, fila por fila."""
    esquema, filas = esquema_y_filas(base, declarado)
    for fila in filas:
        for canonica in canonicas:
            yield esquema.valor(fila, canonica)
