"""Spider de Bodega Aurrera (escalón d, solo listados).

Aurrera corre sobre la misma plataforma que Walmart México: mismo
``__NEXT_DATA__``, mismas facetas, mismos IDs de rama y hoja y el mismo
HUMAN (reconocimiento en ``reconocimiento/aurrera/notas.md``). Por eso hereda
todo de ``SpiderWalmart`` y solo cambia el dominio. Lo que la ficha marca como
distinto no pide código: la URL de la hoja sin el slug de la rama sale tal
cual de ``baseSeoURL``, y la faceta ``cat_id`` en ``contentLayout`` ya la
encuentra la búsqueda recursiva de facetas.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl aurrera
    uv run --project scrapers scrapy crawl aurrera -s CLOSESPIDER_ITEMCOUNT=50
"""
from precios_scrapers.spiders.walmart import SpiderWalmart


class SpiderAurrera(SpiderWalmart):
    name = "aurrera"
    sitio = "https://www.bodegaaurrera.com.mx"
