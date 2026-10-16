"""Spider de Alsuper (escalón a, solo listados).

Estrategia (reconocimiento en ``reconocimiento/alsuper/notas.md``): el sitio
es Angular sobre una API REST propia (``prod.alsuperapi.com``) que solo filtra
por User-Agent: sin uno de navegador responde 403 ``{"message":"Forbidden"}``
y con él responde sin impersonar, cookies ni token. El listado
``/ms-products/branch/{sucursal}?department=…`` trae precio, precio regular,
EAN, marca e imagen, así que no se abren fichas.

El filtro ``department`` no es el ID sino el slug que arma el frontend con la
descripción y el ID (``Farmacia-18``, ``Bebés-15``). Se lee de
``/departments/web`` en cada corrida: si Alsuper renombra un departamento, el
slug cambia y un valor fijo dejaría la categoría vacía.

No se manda ``ecommerce=true``: con él solo salen los productos que se venden
en línea (1,619 de 2,504 en Farmacia) y el legado capturaba todo el surtido.

El precio depende de la sucursal, que va en la ruta. Se fija la de
tiendas.yml (la 6, Alsuper Plus Leones de Chihuahua: la que el sitio asigna
por defecto y la del legado) y va en ``zona_precio``.

Uso, desde la raíz del repo:
    uv run --project scrapers scrapy crawl alsuper
    uv run --project scrapers scrapy crawl alsuper -s CLOSESPIDER_ITEMCOUNT=50
"""
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil

import scrapy
from scrapy.downloadermiddlewares.retry import get_retry_request

from precios_scrapers.spiders.base import SpiderTienda

API = "https://prod.alsuperapi.com"
# 500 por página: sin tope del lado de la API (3,000 trae todo Farmacia en
# 4.3 MB), pero respuestas más chicas pierden menos si una falla.
POR_PAGINA = 500
# El escalón a no pasa por curl_cffi, que es quien pondría el User-Agent; sin
# uno de navegador la API responde 403.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


class SpiderAlsuper(SpiderTienda):
    """Departamentos -> páginas de 500 de la sucursal fija."""

    name = "alsuper"
    custom_settings = {"USER_AGENT": USER_AGENT}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sucursal = self.tienda["sucursal"]

    async def start(self):
        for ident in self.tienda["categorias"]:
            self.sin_datos.add(ident)
        yield scrapy.Request(f"{API}/departments/web?branch={self.sucursal}",
                             callback=self.parse_departamentos)

    def parse_departamentos(self, response):
        slugs = {d["department_id"]: f"{d['description']}-{d['department_id']}"
                 for d in response.json()["data"]}
        for ident in self.tienda["categorias"]:
            # "4:Sueros" es una sola categoría del departamento 4: el alcance
            # v1 toma Sueros sin el resto de Jugos y Bebidas.
            depto, _, categoria = str(ident).partition(":")
            if int(depto) not in slugs:
                # Queda en sin_datos y la alerta de cierre lo reporta.
                self.logger.error("El departamento %s ya no existe", depto)
                continue
            slug = slugs[int(depto)]
            if categoria:
                slug += f"&category={categoria}"
            yield self.pagina(ident, slug, 1)

    def pagina(self, ident: int | str, slug: str,
               numero: int) -> scrapy.Request:
        """``slug`` es el filtro: departamento y, si va, categoría."""
        return scrapy.Request(
            f"{API}/ms-products/branch/{self.sucursal}?department={slug}"
            f"&page={numero}&limit={POR_PAGINA}",
            callback=self.parse,
            cb_kwargs={"ident": ident, "slug": slug, "numero": numero})

    def parse(self, response, ident: int | str, slug: str, numero: int):
        """Una página; la primera pide las demás."""
        try:
            datos = response.json()["data"]
            total = datos["total_items"]
        except (ValueError, KeyError, TypeError):
            self.logger.warning("Página sin listado",
                                extra={"url": response.url})
            self.crawler.stats.inc_value(f"{self.name}/paginas_sin_datos")
            otra = get_retry_request(response.request, spider=self,
                                     reason="pagina_incompleta")
            if otra is not None:
                yield otra
            return
        if numero == 1:
            self.sin_datos.discard(ident)
            self.total_reportado = (self.total_reportado or 0) + total
            self.por_categoria[ident] = {"total_reportado": total,
                                         "skus": set()}
            for siguiente in range(2, ceil(total / POR_PAGINA) + 1):
                yield self.pagina(ident, slug, siguiente)

        ahora = datetime.now(timezone.utc)
        skus = self.por_categoria[ident]["skus"]
        for producto in datos["data"]:
            fila = self.fila(producto, ahora, response.url)
            skus.add(fila["sku_tienda"])
            if "COMODIN" in producto["name"].upper():
                # Código interno de punto de venta ("COMODIN ULTRA LAB GI" a
                # $0.01): los 72 de Farmacia no se venden en línea ni tienen
                # existencia, y el legado no traía ninguno. Cuentan como
                # vistos porque vienen en total_items.
                self.crawler.stats.inc_value(f"{self.name}/comodines")
                continue
            if fila["precio_lista"] is None:
                self.crawler.stats.inc_value(f"{self.name}/sin_precio")
                continue
            yield fila

    def fila(self, producto: dict, ahora: datetime, url_fuente: str) -> dict:
        regular = precio(producto.get("regular_price"))
        venta = precio(producto.get("price"))
        # Sin descuento real, un solo precio en precio_lista (contrato v1).
        if regular is None or venta is None or venta >= regular:
            regular, venta = regular or venta, None
        ean = producto.get("ean")
        ruta = [producto.get(c) for c in
                ("department", "category_name", "subcategory_name")]
        atributos = {"presentacion": producto.get("format"),
                     "promocion": producto.get("promotion")}
        return {
            "capturado_en": ahora,
            "url_producto": producto["share_url"],
            "sku_tienda": str(producto["id"]),
            "producto": producto["name"],
            "marca": producto.get("brand") or None,
            "ean": ean if ean and ean.isdigit() else None,
            "categoria_ruta": [paso for paso in ruta if paso],
            "precio_lista": regular,
            "precio_oferta": venta,
            "moneda": "MXN",
            "disponible": producto.get("stock", 0) > 0,
            "url_imagen": producto.get("image_url") or None,
            "zona_precio": f"sucursal_{self.sucursal}",
            "url_fuente": url_fuente,
            "atributos_tienda": {k: v for k, v in atributos.items() if v},
        }


def precio(valor) -> Decimal | None:
    """Decimal del precio; None si falta o es 0."""
    return Decimal(str(valor)) if valor else None
