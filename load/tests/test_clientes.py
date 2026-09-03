"""Los factories de clientes de Google Cloud leen su configuración de gcp.yml."""

import google.auth.exceptions
import pytest

from precios_load import clientes
from precios_load.config import cargar_config


@pytest.fixture(scope="module")
def cfg():
    return cargar_config()


def _construir(factory, cfg):
    """Crea el cliente, o salta si esta máquina no tiene ADC configurado."""
    try:
        return factory(cfg)
    except google.auth.exceptions.DefaultCredentialsError:
        pytest.skip("ADC no configurado en esta máquina")


def test_cliente_bq_toma_project_y_location_de_config(cfg):
    cliente = _construir(clientes.cliente_bq, cfg)

    assert cliente.project == cfg.project_id
    assert cliente.location == cfg.location


def test_cliente_gcs_toma_project_de_config(cfg):
    cliente = _construir(clientes.cliente_gcs, cfg)

    assert cliente.project == cfg.project_id
