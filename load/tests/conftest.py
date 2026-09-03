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
        list(cliente.list_tables(cfg_gcp.dataset_ops, max_results=1))
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


# Header de los dos archivos "vacíos" de septiembre (solo encabezado, 0 filas).
HEADER_SOLO_CSV = (
    b"SKU,URL_PRODUCTO,Producto,Precio_Actual,Precio_Oferta,"
    b"URL_IMAGEN,Fecha_Hora_Captura,Tienda\n"
)

# Una fila de datos válida para ese header (variante V1). La fecha cae en el
# mes por defecto de `fuente_falsa` (2026-06), así que no marca desfase.
FILA_CSV = (
    b"900437,https://tienda.mx/x/p,Cubrebocas,41.90,39.90,"
    b"https://img/x,2026-06-14 20:31:07,Tienda\n"
)


def csv_valido(n_filas: int = 2) -> bytes:
    """Un CSV V1 con header y `n_filas` filas de datos, para los tests de bronce."""
    return HEADER_SOLO_CSV + FILA_CSV * n_filas


def fuente_falsa(
    contenido: bytes,
    nombre: str | None = None,
    tienda: str = "__test__",
    anio_mes: str = "2026-06",
):
    """Un `ArchivoFuente` sintético para los tests de raw e ingesta.

    `tienda="__test__"` mantiene los objetos de prueba fuera de las particiones
    reales de las tiendas en `gs://<bucket_raw>`.
    """
    import hashlib
    from uuid import uuid4

    from precios_load.config import ArchivoDeclarado
    from precios_load.descubrimiento import ArchivoFuente

    nombre = nombre or f"detalle_{uuid4().hex[:8]}.csv"
    carpeta = f"{anio_mes[:4]}/{anio_mes[5:]}_mes"
    ruta = f"{carpeta}/{nombre}"
    declarado = ArchivoDeclarado(ruta=ruta, tienda=tienda, anio_mes=anio_mes)
    return ArchivoFuente(
        ruta=ruta,
        tienda=tienda,
        anio_mes=anio_mes,
        bytes=len(contenido),
        md5=hashlib.md5(contenido).hexdigest(),
        filas=0 if contenido.count(b"\n") <= 1 else contenido.count(b"\n") - 1,
        variante="V4",
        declarado=declarado,
    )


@pytest.fixture
def base_local(tmp_path):
    """Escribe el contenido de un `ArchivoFuente` en un `salida/data` de mentira."""

    def _escribir(fuente, contenido: bytes) -> str:
        (tmp_path / os.path.dirname(fuente.ruta)).mkdir(parents=True, exist_ok=True)
        (tmp_path / fuente.ruta).write_bytes(contenido)
        return str(tmp_path)

    return _escribir


@pytest.fixture
def limpiar_raw(cliente_gcs, cfg_gcp):
    """Borra de `gs://<bucket_raw>` los objetos cuyas URIs registre el test."""
    uris: list[str] = []
    yield uris.append
    for uri in uris:
        objeto = uri.removeprefix(f"gs://{cfg_gcp.bucket_raw}/")
        blob = cliente_gcs.bucket(cfg_gcp.bucket_raw).blob(objeto)
        if blob.exists():
            blob.delete()


@pytest.fixture
def limpiar_bronce(cliente_gcs, cfg_gcp):
    """Borra de `gs://<bucket_bronce>` los objetos cuyas URIs registre el test.

    Salta el test si el bucket de bronce no es alcanzable: `cliente_gcs` solo
    comprueba el de raw.
    """
    try:
        if not cliente_gcs.bucket(cfg_gcp.bucket_bronce).exists():
            pytest.skip(f"El bucket {cfg_gcp.bucket_bronce} no existe o no es visible")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Cloud Storage (bronce) no disponible: {e}")

    uris: list[str] = []
    yield uris.append
    for uri in uris:
        objeto = uri.removeprefix(f"gs://{cfg_gcp.bucket_bronce}/")
        blob = cliente_gcs.bucket(cfg_gcp.bucket_bronce).blob(objeto)
        if blob.exists():
            blob.delete()


@pytest.fixture
def tabla_manifest_tmp(cliente_bq, cfg_gcp):
    """Nombre de una tabla de manifest desechable, borrada al terminar el test.

    Nunca se toca `_ingesta_manifest` de verdad: eso corrompería el estado de
    idempotencia de la ingesta real.
    """
    nombre = f"_ingesta_manifest_test_{uuid4().hex[:8]}"
    yield nombre
    cliente_bq.delete_table(cfg_gcp.tabla_ops(nombre), not_found_ok=True)


@pytest.fixture
def tabla_ext_tmp(cliente_bq, cfg_gcp):
    """Nombre de una external table desechable en el dataset de bronce.

    La real (`precios_ext`) apunta al mismo prefijo de GCS, así que se prueba
    contra una copia con otro nombre y se borra en el teardown.
    """
    nombre = f"precios_ext_test_{uuid4().hex[:8]}"
    yield nombre
    cliente_bq.delete_table(cfg_gcp.tabla_bronce(nombre), not_found_ok=True)


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
