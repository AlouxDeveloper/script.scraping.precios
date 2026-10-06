"""Resolución de la raíz del repo.

Igual que los scrapers de `extract/`, todos los comandos se ejecutan desde la
raíz del repo y las rutas de datos son relativas a ella (`./salida/...`).
Aquí se verifica esa premisa en vez de dejar que falle más tarde con un
directorio vacío.
"""

import os

# Marcadores que solo existen juntos en la raíz del repo.
MARCADORES = ("load/pyproject.toml", "extract/pyproject.toml")


def raiz_repo() -> str:
    """Devuelve el directorio actual si es la raíz del repo; si no, aborta."""
    actual = os.getcwd()
    faltantes = [m for m in MARCADORES if not os.path.exists(os.path.join(actual, m))]
    if faltantes:
        raise SystemExit(
            f"❌ Este comando debe ejecutarse desde la raíz del repo.\n"
            f"   Directorio actual: {actual}\n"
            f"   No se encontró: {', '.join(faltantes)}\n"
            f"   Usa: uv run --project load python -m precios_load.cli <comando>"
        )
    return actual
