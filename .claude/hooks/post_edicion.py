"""Hook PostToolUse de Claude Code para Edit y Write.

Valida en caliente lo que se acaba de editar, para no descubrir el error
hasta el siguiente build:

- .sql/.yml del proyecto dbt: `dbt parse` (~3 s). Atrapa YAML mal formado,
  refs rotos y Jinja inválido.
- .py: `ruff check --select E9,F` (sintaxis y errores reales: nombres sin
  definir, imports sin usar), sin agregar ruff como dependencia. No se
  revisa estilo: los scrapers viejos llenarían de ruido cada edición.

Si falla, sale con código 2 y el error llega a Claude; la edición no se
revierte.
"""

import json
import os
import subprocess
import sys

DBT = "transform/dbt/precios"


def validar(ruta, raiz):
    """Corre la validación que toca según el archivo; regresa (ok, salida)."""
    relativa = os.path.relpath(ruta, raiz)
    if relativa.startswith(DBT) and relativa.endswith((".sql", ".yml", ".yaml")):
        comando = ["uv", "run", "--project", "transform", "dbt", "parse",
                   "--project-dir", DBT, "--profiles-dir", DBT, "--quiet"]
    elif relativa.endswith(".py"):
        comando = ["uvx", "ruff", "check", "--quiet", "--select", "E9,F",
                   relativa]
    else:
        return True, ""
    resultado = subprocess.run(comando, cwd=raiz, capture_output=True, check=False,
                               text=True, timeout=120)
    return resultado.returncode == 0, resultado.stdout + resultado.stderr


def main():
    evento = json.load(sys.stdin)
    ruta = evento.get("tool_input", {}).get("file_path", "")
    raiz = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    if not ruta or not ruta.startswith(raiz):
        return
    ok, salida = validar(ruta, raiz)
    if not ok:
        # Las últimas líneas bastan; dbt imprime un encabezado largo.
        cola = "\n".join(salida.strip().splitlines()[-25:])
        print(f"Validación falló tras editar {ruta}:\n{cola}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
