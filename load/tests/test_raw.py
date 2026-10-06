"""La capa raw: el CSV original subido a GCS byte por byte.

Integración real contra `gs://<bucket_raw>`. Los objetos se suben bajo
`tienda=__test__/` y se borran en el teardown (`limpiar_raw`).
"""

import base64
from dataclasses import replace

import pytest

from tests.conftest import HEADER_SOLO_CSV, fuente_falsa

from precios_load import raw


def test_subir_deja_objeto_byte_identico_en_la_ruta_particionada(
    cliente_gcs, cfg_gcp, base_local, limpiar_raw
):
    contenido = b"sku,precio\n900437,41.90\n"
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)

    uri = raw.subir(cliente_gcs, cfg_gcp, fuente, base=base)
    limpiar_raw(uri)

    assert uri == cfg_gcp.uri_raw("__test__", "2026-06", fuente.nombre)
    assert "/precios/tienda=__test__/anio_mes=2026-06/" in uri

    objeto = uri.removeprefix(f"gs://{cfg_gcp.bucket_raw}/")
    blob = cliente_gcs.bucket(cfg_gcp.bucket_raw).get_blob(objeto)
    assert base64.b64decode(blob.md5_hash).hex() == fuente.md5


def test_subir_un_archivo_solo_con_header_tambien_sube(
    cliente_gcs, cfg_gcp, base_local, limpiar_raw
):
    """Raw es fiel: los archivos vacíos de septiembre también se suben."""
    fuente = fuente_falsa(HEADER_SOLO_CSV)
    base = base_local(fuente, HEADER_SOLO_CSV)

    uri = raw.subir(cliente_gcs, cfg_gcp, fuente, base=base)
    limpiar_raw(uri)

    objeto = uri.removeprefix(f"gs://{cfg_gcp.bucket_raw}/")
    blob = cliente_gcs.bucket(cfg_gcp.bucket_raw).get_blob(objeto)
    assert blob.size == len(HEADER_SOLO_CSV)
    assert base64.b64decode(blob.md5_hash).hex() == fuente.md5


def test_subir_lanza_error_si_el_md5_no_coincide(
    cliente_gcs, cfg_gcp, base_local, limpiar_raw
):
    contenido = b"contenido real del archivo"
    fuente = fuente_falsa(contenido)
    base = base_local(fuente, contenido)
    limpiar_raw(cfg_gcp.uri_raw("__test__", "2026-06", fuente.nombre))

    mentirosa = replace(fuente, md5="0" * 32)
    with pytest.raises(raw.ErrorSubidaRaw):
        raw.subir(cliente_gcs, cfg_gcp, mentirosa, base=base)
