"""Humo del CLI: el esqueleto responde y expone todos los comandos."""

from typer.testing import CliRunner

from precios_load.cli import app

runner = CliRunner()


def test_help_lista_los_comandos():
    resultado = runner.invoke(app, ["--help"])
    assert resultado.exit_code == 0
    for comando in ("plan", "ingesta", "bq-setup", "estado"):
        assert comando in resultado.stdout
