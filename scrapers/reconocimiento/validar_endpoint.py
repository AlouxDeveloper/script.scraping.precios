"""Valida un endpoint candidato con tráfico mínimo y deja evidencia en CSV.

Implementa la sección 4 de la Metodología de reconocimiento: pide la misma
URL sin impersonar y luego impersonando Chrome, y agrega una fila por
petición a ``scrapers/reconocimiento/<slug>/validacion.csv``. La
clasificación de cada señal (bloqueo o error normal) la hace una persona con
la tabla de esa sección; el script solo registra lo que observa.

Uso, desde la raíz del repo:
    uv run --project scrapers python scrapers/reconocimiento/validar_endpoint.py \
        --slug guadalajara --url "https://www.farmaciasguadalajara.com/robots.txt" -n 5
"""
import argparse
import csv
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

# Firmas de bloqueo vistas en el repo y en la documentación de cada proveedor.
# Un 200 con una de estas firmas en el cuerpo también es bloqueo (caso HEB).
FIRMAS_BLOQUEO = ("captcha", "incapsula", "access denied", "_pxhd", "cf-chl")
# Regla de tráfico de la Metodología: como máximo 20 peticiones por endpoint
# y variante. Va fija en el código para que ningún argumento la rebase.
TOPE_PETICIONES = 20


def probar(url: str, perfil: str | None) -> dict:
    """Hace una petición; perfil=None es HTTP sin impersonación."""
    inicio = time.monotonic()
    try:
        # Sin seguir redirects: un 302 hacia una página de bloqueo o de
        # CAPTCHA es una señal y debe quedar registrado como tal.
        r = requests.get(url, impersonate=perfil, timeout=30,
                         allow_redirects=False)
    except Exception as error:  # Reset HTTP/2, TLS cerrado, timeout.
        return {"status": "ERROR", "detalle": str(error)[:120],
                "segundos": round(time.monotonic() - inicio, 2), "bytes": 0}
    cuerpo = r.text[:5000].lower()
    firma = next((f for f in FIRMAS_BLOQUEO if f in cuerpo), "")
    return {"status": r.status_code,
            "detalle": firma or r.headers.get("location", ""),
            "segundos": round(time.monotonic() - inicio, 2),
            "bytes": len(r.content)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--slug", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("-n", type=int, default=5)
    p.add_argument("--pausa", type=float, default=2.0)
    a = p.parse_args()
    salida = Path(f"scrapers/reconocimiento/{a.slug}/validacion.csv")
    salida.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not salida.exists()
    campos = ["fecha", "perfil", "url", "status", "detalle", "segundos", "bytes"]
    # Modo append: las corridas sucesivas (otro día, otro endpoint) se
    # acumulan en el mismo archivo de evidencia de la tienda.
    with salida.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        if nuevo:
            w.writeheader()
        for perfil in (None, "chrome"):
            tiempos = []
            for _ in range(min(a.n, TOPE_PETICIONES)):
                fila = probar(a.url, perfil)
                tiempos.append(fila["segundos"])
                w.writerow({"fecha": datetime.now(timezone.utc).isoformat(),
                            "perfil": perfil or "sin_impersonar",
                            "url": a.url, **fila})
                # Pausa mínima de 1 s entre peticiones aunque se pida menos.
                time.sleep(max(a.pausa, 1.0))
            print(perfil or "sin_impersonar",
                  "p50:", statistics.median(tiempos), "s; max:", max(tiempos), "s")


if __name__ == "__main__":
    main()
