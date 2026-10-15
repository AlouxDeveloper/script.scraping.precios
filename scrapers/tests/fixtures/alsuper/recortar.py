"""Recorta una página de ``ms-products`` de Alsuper a un fixture de pruebas.

Deja ``total_items`` y las primeras ``n`` filas más las que traen oferta
(``price`` menor que ``regular_price``), que son el caso borde, sin las
facetas ni los textos largos. Una página de 500 productos pesa ~850 KB.

Uso, con una página guardada por una sonda (fuera de git):
    uv run --project scrapers python \\
        scrapers/tests/fixtures/alsuper/recortar.py pagina.json \\
        scrapers/tests/fixtures/alsuper/<nombre>.json [n]
"""
import json
import sys

PRODUCTO = ("id", "sku", "ean", "name", "brand", "format", "price",
            "regular_price", "stock", "image_url", "share_url", "department",
            "category_name", "subcategory_name", "promotion")


def recortar(pagina: dict, n: int) -> dict:
    productos = pagina["data"]["data"]
    bordes = [p for p in productos[n:] if p["price"] < p["regular_price"]]
    return {"data": {"total_items": pagina["data"]["total_items"],
                     "data": [{k: p.get(k) for k in PRODUCTO}
                              for p in [*productos[:n], *bordes[:2]]]}}


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        pagina = json.load(f)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(recortar(pagina, n), f, ensure_ascii=False, indent=1)
