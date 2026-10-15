"""Recorta una página de búsqueda OCC de San Pablo a un fixture de pruebas.

Deja la paginación, las facetas con códigos de categoría (la que decide la
partición) y las primeras ``n`` filas más las que traen descuento
(``basePrice`` menor que ``price``), que son el caso borde. Una página de 100
productos con ``fields=FULL`` pesa ~290 KB.

Uso, con una página guardada por una sonda (fuera de git):
    uv run --project scrapers python \\
        scrapers/tests/fixtures/san_pablo/recortar.py pagina.json \\
        scrapers/tests/fixtures/san_pablo/<nombre>.json [n]
"""
import json
import sys

PRODUCTO = ("code", "name", "brandName", "url", "price", "basePrice",
            "images", "additionalDescription", "availableForPurchase")


def recortar(pagina: dict, n: int) -> dict:
    productos = pagina["products"]
    bordes = [p for p in productos[n:]
              if p["basePrice"]["value"] < p["price"]["value"]]
    facetas = [{"values": [v for v in f["values"]
                           if v["name"].isdigit() or "-" in v["name"]]}
               for f in pagina.get("facets", []) if f.get("name") is None]
    return {
        "pagination": pagina["pagination"],
        "facets": facetas,
        "products": [{k: p[k] for k in PRODUCTO if k in p}
                     for p in [*productos[:n], *bordes[:2]]],
    }


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        pagina = json.load(f)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(recortar(pagina, n), f, ensure_ascii=False, indent=1)
