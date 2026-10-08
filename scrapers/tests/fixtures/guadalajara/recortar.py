"""Recorta una página de listado de Guadalajara a un fixture de pruebas.

Deja solo lo que lee el spider: la miga de pan, el texto "N productos" y las
primeras ``n`` tarjetas más las que tengan promoción o no traigan marca, que
son los casos borde. Las páginas completas de 96 tarjetas pesan ~2 MB.

Uso, con una página guardada por una sonda (fuera de git):
    uv run --project scrapers python \\
        scrapers/tests/fixtures/guadalajara/recortar.py pagina.html \\
        scrapers/tests/fixtures/guadalajara/<nombre>.html [n]
"""
import re
import sys

from parsel import Selector


def recortar(html: str, n: int) -> str:
    pagina = Selector(text=html)
    tarjetas = pagina.css("div.product[data-pid]")
    bordes = [t for t in tarjetas[n:]
              if "".join(t.css(".promotions ::text").getall()).strip()
              or not (t.css(".plp-brand::text").get() or "").strip()]
    total = re.search(r"[\d,]+\s+productos", html).group(0)
    partes = [pagina.css(".breadcrumb").get(),
              f'<span class="result-count">{total}</span>',
              *(t.get() for t in [*tarjetas[:n], *bordes[:2]])]
    return "<html><body>\n" + "\n".join(partes) + "\n</body></html>\n"


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        html = f.read()
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(recortar(html, n))
