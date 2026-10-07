"""Recorta una página de listado de Walmart a un fixture de pruebas.

Deja solo el ``__NEXT_DATA__`` con lo que lee el spider: conteos, paginación,
breadcrumb, facetas ``cat_id`` y ``price`` (en su ruta original) y los campos
usados de cada ítem. Las páginas completas pesan ~1-2 MB.

Uso, con una página guardada por una sonda (salida/, fuera de git):
    uv run --project scrapers python scrapers/tests/fixtures/walmart/recortar.py \\
        pagina.html scrapers/tests/fixtures/walmart/<nombre>.html
"""
import json
import re
import sys

BUSQUEDA = {"aggregatedCount", "breadCrumb", "paginationV2", "itemStacks"}
PAGINACION = {"maxPage", "pageProperties"}
PROPIEDADES = {"stores", "page", "min_price", "max_price", "cat_id"}
ITEM = {"__typename", "usItemId", "name", "brand", "canonicalUrl", "price",
        "priceInfo", "availabilityStatusV2", "sellerName", "sellerType",
        "imageInfo", "isSponsoredFlag"}
PRECIO = {"linePrice", "wasPrice", "priceRangeString"}
FACETAS = {"cat_id", "price"}


def podar(nodo):
    """Conserva solo las ramas que llevan a ``allSortAndFilterFacets``."""
    if isinstance(nodo, dict):
        if nodo.get("allSortAndFilterFacets"):
            return {"allSortAndFilterFacets": [
                f for f in nodo["allSortAndFilterFacets"]
                if f["type"] in FACETAS]}
        hijos = {k: podar(v) for k, v in nodo.items()}
        return {k: v for k, v in hijos.items() if v} or None
    if isinstance(nodo, list):
        hijos = [podar(v) for v in nodo]
        return hijos if any(hijos) else None
    return None


def recortar(html: str) -> str:
    texto = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                      html, re.S).group(1)
    datos = json.loads(texto)["props"]["pageProps"]["initialData"]
    busqueda = {k: datos["searchResult"][k] for k in BUSQUEDA}
    pag = busqueda["paginationV2"]
    busqueda["paginationV2"] = {
        "maxPage": pag["maxPage"],
        "pageProperties": {k: v for k, v in pag["pageProperties"].items()
                           if k in PROPIEDADES}}
    for pila in busqueda["itemStacks"]:
        pila["items"] = [{k: v for k, v in item.items() if k in ITEM}
                         for item in pila["items"]]
        for item in pila["items"]:
            if "priceInfo" in item:
                item["priceInfo"] = {k: v for k, v in item["priceInfo"].items()
                                     if k in PRECIO}
            if "imageInfo" in item:
                item["imageInfo"] = {"thumbnailUrl":
                                     item["imageInfo"]["thumbnailUrl"]}
    resto = {k: v for k, v in datos.items() if k != "searchResult"}
    inicial = {"searchResult": busqueda, **(podar(resto) or {})}
    busqueda.update(podar({"modules": datos["searchResult"].get("modules")})
                    or {})
    nuevo = {"props": {"pageProps": {"initialData": inicial}}}
    return ('<html><body><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(nuevo, ensure_ascii=False) + "</script></body></html>\n")


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        html = f.read()
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(recortar(html))
