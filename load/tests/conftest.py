"""Fixtures y ayudas compartidas por los tests que tocan el histórico real.

`salida/` está en `.gitignore`: si no existe localmente, los tests que
dependen de él se saltan en vez de fallar. Lo mismo con Google Cloud: sin
credenciales ADC, los tests de integración se saltan en vez de fallar.
"""

import csv
import os
from uuid import uuid4

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


@pytest.fixture(scope="session")
def cfg_gcp():
    """La configuración de `gcp.yml`, leída una sola vez por sesión."""
    return cargar_config()


@pytest.fixture(scope="session")
def cliente_bq(cfg_gcp):
    """Cliente de BigQuery real, o salta si esta máquina no puede alcanzarlo.

    Fuerza una llamada de red (`list_tables`) para que la falta de credenciales
    o de conectividad se convierta en un `skip` aquí y no en un error opaco a
    mitad de cada test.
    """
    from precios_load.clientes import cliente_bq as _factory

    try:
        cliente = _factory(cfg_gcp)
        list(cliente.list_tables(cfg_gcp.dataset, max_results=1))
    except Exception as e:  # noqa: BLE001 - cualquier fallo de infra es un skip
        pytest.skip(f"BigQuery no disponible: {e}")
    return cliente


@pytest.fixture(scope="session")
def cliente_gcs(cfg_gcp):
    """Cliente de Cloud Storage real, o salta si el bucket raw no es alcanzable."""
    from precios_load.clientes import cliente_gcs as _factory

    try:
        cliente = _factory(cfg_gcp)
        if not cliente.bucket(cfg_gcp.bucket_raw).exists():
            pytest.skip(f"El bucket {cfg_gcp.bucket_raw} no existe o no es visible")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Cloud Storage no disponible: {e}")
    return cliente


@pytest.fixture
def tabla_manifest_tmp(cliente_bq, cfg_gcp):
    """Nombre de una tabla de manifest desechable, borrada al terminar el test.

    Nunca se toca `_ingesta_manifest` de verdad: eso corrompería el estado de
    idempotencia de la ingesta real.
    """
    nombre = f"_ingesta_manifest_test_{uuid4().hex[:8]}"
    yield nombre
    cliente_bq.delete_table(cfg_gcp.tabla(nombre), not_found_ok=True)


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
