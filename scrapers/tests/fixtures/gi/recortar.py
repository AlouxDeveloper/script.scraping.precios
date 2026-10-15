"""Recorta páginas de la Store API de GI a un fixture de pruebas.

Deja las primeras ``n`` filas de la primera página más los casos borde que
haya en cualquiera de las páginas dadas: sin SKU, precio 0 y nombre con
entidades HTML. Quita descripciones y ``srcset``; una página de 100
productos pesa ~300 KB.

Uso, con páginas guardadas por una sonda (fuera de git):
    uv run --project scrapers python \\
        scrapers/tests/fixtures/gi/recortar.py salida.json pagina.json \\
        [otra.json ...]
"""
import json
import sys

PRODUCTO = ("id", "name", "permalink", "sku", "prices", "images",
            "categories", "brands", "is_in_stock")


def recortar(paginas: list[list[dict]], n: int = 3) -> list[dict]:
    todos = [p for pagina in paginas for p in pagina]
    bordes = [next((p for p in todos if regla(p)), None) for regla in (
        lambda p: not p["sku"],
        lambda p: p["prices"]["price"] in ("", "0"),
        lambda p: "&#" in p["name"])]
    salida = []
    for p in [*paginas[0][:n], *(b for b in bordes if b)]:
        corto = {k: p[k] for k in PRODUCTO}
        corto["images"] = [{"src": i["src"]} for i in p["images"][:1]]
        corto["categories"] = [{"id": c["id"], "name": c["name"]}
                               for c in p["categories"]]
        salida.append(corto)
    return salida


if __name__ == "__main__":
    paginas = []
    for ruta in sys.argv[2:]:
        with open(ruta, encoding="utf-8") as f:
            paginas.append(json.load(f))
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(recortar(paginas), f, ensure_ascii=False, indent=1)
