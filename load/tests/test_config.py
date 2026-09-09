"""La configuración debe fallar temprano y nombrando el campo que está mal."""

import re
import textwrap

import pytest

from precios_load.config import ErrorConfig, cargar_config

YML_VALIDO = """
project_id: proyecto-de-prueba
location: US
bucket_raw: raw_precios_bitek
bucket_bronce: bronce_precios_bitek
prefijo: precios
dataset_bronce: precios_bronce
dataset_ops: precios_ops
conexion_biglake: precios_biglake
ruta_local_datos: ./salida/data
prefijo_catalogos: catalogos
ruta_local_catalogos: ./salida/catalogos
anio_mes_maximo: "2026-08"
"""


def escribir(tmp_path, contenido, monkeypatch):
    """Deja un gcp.yml de prueba y hace que raiz_repo apunte a su carpeta."""
    (tmp_path / "load" / "config").mkdir(parents=True)
    (tmp_path / "load" / "config" / "gcp.yml").write_text(
        textwrap.dedent(contenido), encoding="utf-8"
    )
    monkeypatch.setattr("precios_load.config.raiz_repo", lambda: str(tmp_path))
    return "load/config/gcp.yml"


def test_carga_valida(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, YML_VALIDO, monkeypatch)
    config = cargar_config(ruta)

    assert config.project_id == "proyecto-de-prueba"
    assert config.uri_raw("chedraui", "2026-09", "scraping_detalle_chedraui.csv") == (
        "gs://raw_precios_bitek/precios/tienda=chedraui/anio_mes=2026-09"
        "/scraping_detalle_chedraui.csv"
    )
    assert config.prefijo_bronce() == "gs://bronce_precios_bitek/precios"
    assert config.uri_raw_catalogo("ndf/dim_ndf.xlsx") == (
        "gs://raw_precios_bitek/catalogos/ndf/dim_ndf.xlsx"
    )
    assert config.uri_bronce_catalogo("ndf/dim_ndf.parquet") == (
        "gs://bronce_precios_bitek/catalogos/ndf/dim_ndf.parquet"
    )
    assert config.prefijo_bronce_catalogos() == "gs://bronce_precios_bitek/catalogos"
    assert config.conexion() == "proyecto-de-prueba.us.precios_biglake"
    assert config.tabla_bronce("precios_ext") == "proyecto-de-prueba.precios_bronce.precios_ext"
    assert config.tabla_ops("_ingesta_manifest") == "proyecto-de-prueba.precios_ops._ingesta_manifest"
    assert config.anio_mes_maximo == "2026-08"


def test_campo_faltante_nombra_el_campo_y_el_archivo(tmp_path, monkeypatch):
    sin_dataset = YML_VALIDO.replace("dataset_ops: precios_ops\n", "")
    ruta = escribir(tmp_path, sin_dataset, monkeypatch)

    with pytest.raises(ErrorConfig) as e:
        cargar_config(ruta)

    assert "dataset_ops" in str(e.value)
    assert "gcp.yml" in str(e.value)


def test_campo_vacio_falla(tmp_path, monkeypatch):
    vacio = YML_VALIDO.replace("project_id: proyecto-de-prueba", 'project_id: "   "')
    ruta = escribir(tmp_path, vacio, monkeypatch)

    with pytest.raises(ErrorConfig, match="project_id"):
        cargar_config(ruta)


def test_campo_nulo_falla(tmp_path, monkeypatch):
    nulo = YML_VALIDO.replace("project_id: proyecto-de-prueba", "project_id:")
    ruta = escribir(tmp_path, nulo, monkeypatch)

    with pytest.raises(ErrorConfig, match="project_id"):
        cargar_config(ruta)


def test_campo_desconocido_falla(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, YML_VALIDO + "bucket_plata: plata\n", monkeypatch)

    with pytest.raises(ErrorConfig, match="bucket_plata"):
        cargar_config(ruta)


def test_location_invalida_falla(tmp_path, monkeypatch):
    ruta = escribir(tmp_path, YML_VALIDO.replace("location: US", "location: us"), monkeypatch)

    with pytest.raises(ErrorConfig, match="location"):
        cargar_config(ruta)


def test_bucket_con_uri_completa_falla(tmp_path, monkeypatch):
    con_uri = YML_VALIDO.replace(
        "bucket_raw: raw_precios_bitek", "bucket_raw: gs://raw_precios_bitek"
    )
    ruta = escribir(tmp_path, con_uri, monkeypatch)

    with pytest.raises(ErrorConfig, match="bucket_raw"):
        cargar_config(ruta)


def test_ruta_absoluta_falla(tmp_path, monkeypatch):
    absoluta = YML_VALIDO.replace("ruta_local_datos: ./salida/data", "ruta_local_datos: /salida/data")
    ruta = escribir(tmp_path, absoluta, monkeypatch)

    with pytest.raises(ErrorConfig, match="ruta_local_datos"):
        cargar_config(ruta)


def test_archivo_inexistente_falla(tmp_path, monkeypatch):
    escribir(tmp_path, YML_VALIDO, monkeypatch)

    with pytest.raises(ErrorConfig, match="no_existe.yml"):
        cargar_config("load/config/no_existe.yml")


# --- Catálogos -------------------------------------------------------------


@pytest.mark.parametrize("campo", ["prefijo_catalogos", "ruta_local_catalogos"])
def test_campo_de_catalogos_faltante_falla(tmp_path, monkeypatch, campo):
    sin_campo = re.sub(rf"^{campo}:.*\n", "", YML_VALIDO, flags=re.MULTILINE)
    ruta = escribir(tmp_path, sin_campo, monkeypatch)

    with pytest.raises(ErrorConfig) as e:
        cargar_config(ruta)

    assert campo in str(e.value)
    assert "gcp.yml" in str(e.value)


def test_ruta_de_catalogos_absoluta_falla(tmp_path, monkeypatch):
    absoluta = YML_VALIDO.replace(
        "ruta_local_catalogos: ./salida/catalogos",
        "ruta_local_catalogos: /salida/catalogos",
    )
    ruta = escribir(tmp_path, absoluta, monkeypatch)

    with pytest.raises(ErrorConfig, match="ruta_local_catalogos"):
        cargar_config(ruta)


def test_los_catalogos_no_caen_bajo_el_prefijo_de_precios(tmp_path, monkeypatch):
    """`precios_ext` apunta a `<prefijo_bronce>/*`: los catálogos quedan fuera."""
    ruta = escribir(tmp_path, YML_VALIDO, monkeypatch)
    config = cargar_config(ruta)

    assert not config.prefijo_bronce_catalogos().startswith(
        config.prefijo_bronce() + "/"
    )


# --- Corte de mes -----------------------------------------------------------


@pytest.mark.parametrize("valor", ["2026-8", "agosto", "2026-13", "2026-08-01", "26-08"])
def test_anio_mes_maximo_mal_formado_falla(tmp_path, monkeypatch, valor):
    ruta = escribir(tmp_path, YML_VALIDO.replace("2026-08", valor), monkeypatch)

    with pytest.raises(ErrorConfig, match="anio_mes_maximo"):
        cargar_config(ruta)


def test_el_gcp_yml_real_declara_el_corte():
    """El corte vive en la configuración, no en el código."""
    from precios_load.config import cargar_config as cargar_real

    assert cargar_real().anio_mes_maximo == "2026-08"
