"""Hook PreToolUse de Claude Code para el tool Bash.

Bloquea (exit 2) los comandos que las reglas del proyecto reservan a Aldo:
tocar el historial de git, borrar en BigQuery y el --full-refresh que
recrearía el banco de embeddings ya pagado. El mensaje de stderr le llega a
Claude como la razón del bloqueo.
"""

import json
import re
import sys

# Solo cuenta si git/bq es el comando que se ejecuta (inicio o tras ; & |),
# no si la palabra aparece dentro de un grep, un echo o un mensaje.
INICIO = r"(?:^|[;&|(]\s*)"

REGLAS = [
    (INICIO + r"git\s+(?:-C\s+\S+\s+)?(add|commit|push|reset|rebase)\b",
     ("git add/commit/push/reset/rebase los hace Aldo a mano: deja los "
      "cambios en el working tree y sugiere el mensaje de commit en el chat.")),
    (INICIO + r"bq\s+rm\b",
     "Los borrados en BigQuery los corre Aldo: pásale el comando exacto."),
]


def motivo_bloqueo(comando):
    """Regresa el motivo si el comando está prohibido, o None."""
    for patron, motivo in REGLAS:
        if re.search(patron, comando):
            return motivo
    # DROP/DELETE/TRUNCATE solo cuentan dentro de una consulta a BigQuery:
    # la misma palabra en un grep o en un archivo no borra nada.
    if re.search(INICIO + r"bq\s+query\b", comando) and re.search(
            r"\b(drop|delete\s+from|truncate)\b", comando, re.IGNORECASE):
        return ("DROP/DELETE/TRUNCATE en BigQuery los corre Aldo: pásale el "
                "comando exacto.")
    if "--full-refresh" in comando and (
            "emb_texto" in comando
            or not re.search(r"(--select|\s-s)\s", comando)):
        return ("--full-refresh sin --select, o sobre emb_texto, recrearía el "
                "banco de embeddings pagado. Selecciona los modelos explícitos.")
    return None


def main():
    evento = json.load(sys.stdin)
    comando = evento.get("tool_input", {}).get("command", "")
    motivo = motivo_bloqueo(comando)
    if motivo:
        print(f"Bloqueado por el hook del proyecto: {motivo}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
