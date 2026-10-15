"""Recorta una página de ``catalog_system`` de VTEX a un fixture de pruebas.

Sirve para todas las tiendas de la base VTEX (Chedraui, Farmatodo…): la
respuesta tiene la misma forma.

Deja solo los campos que lee el spider y las primeras ``n`` filas más las que
traen descuento (``ListPrice`` mayor que ``Price``) o precio 0, que son los
casos borde. Una página de 50 productos completa pesa ~1 MB por las
especificaciones y descripciones.

Uso, con una página guardada por una sonda (fuera de git):
    uv run --project scrapers python \\
        scrapers/tests/fixtures/chedraui/recortar.py pagina.json \\
        scrapers/tests/fixtures/<tienda>/<nombre>.json [n]
"""
import json
import sys

PRODUCTO = ("productId", "productName", "productReference", "brand", "link",
            "categories")
ITEM = ("itemId", "ean", "images", "sellers")


def recortar(productos: list[dict], n: int) -> list[dict]:
    def oferta(p):
        return p["items"][0]["sellers"][0]["commertialOffer"]

    bordes = [p for p in productos[n:] if p.get("items")
              and (oferta(p)["ListPrice"] > oferta(p)["Price"]
                   or not oferta(p)["Price"])]
    salida = []
    for p in [*productos[:n], *bordes[:2]]:
        corto = {k: p[k] for k in PRODUCTO if k in p}
        corto["items"] = []
        for item in p["items"][:1]:
            item = {k: item[k] for k in ITEM if k in item}
            item["images"] = item["images"][:1]
            item["sellers"] = [
                {"sellerId": s["sellerId"],
                 "commertialOffer": {k: s["commertialOffer"][k] for k in
                                     ("Price", "ListPrice", "IsAvailable")}}
                for s in item["sellers"]]
            corto["items"].append(item)
        salida.append(corto)
    return salida


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        productos = json.load(f)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(recortar(productos, n), f, ensure_ascii=False, indent=1)
