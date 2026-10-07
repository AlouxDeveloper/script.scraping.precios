"""Pipeline que valida cada ítem contra el contrato v1 y deduplica la corrida.

Reglas: PRD, sección 4.3. Un ítem rechazado se descarta, se cuenta en las
stats (``contrato/rechazados`` y ``contrato/rechazados/<regla>``) y deja una
línea WARNING con la regla y la URL, nunca con el ítem completo. Los
duplicados por (``sku_tienda``, ``zona_precio``) se cuentan aparte en
``contrato/duplicados``.
"""
import logging
import re
from datetime import timedelta

import pyarrow as pa
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from precios_scrapers.contrato import CONTRATO_VERSION, ESQUEMA

# Centinelas que el legado escribía cuando no encontraba el SKU.
SKU_CENTINELAS = {"", "n/a", "search"}
ESCALONES = {"a", "b", "c", "d"}
PATRON_CORRIDA = re.compile(r"^[a-z0-9_]+_\d{8}T\d{4}Z$")

logger = logging.getLogger(__name__)


def validar(item: dict, tienda: str) -> str | None:
    """Devuelve la regla que rompe ``item`` o None si cumple el contrato.

    Las reglas de negocio suponen tipos correctos, por eso van después de
    las de esquema.
    """
    desconocidos = set(item) - set(ESQUEMA.names)
    if desconocidos:
        return "campo_desconocido"
    for campo in ESQUEMA:
        valor = item.get(campo.name)
        if valor is None:
            if not campo.nullable:
                return f"nulo/{campo.name}"
            continue
        # pyarrow convierte un texto suelto en lista de letras.
        if pa.types.is_list(campo.type) and not isinstance(valor, list):
            return f"tipo/{campo.name}"
        try:
            pa.array([valor], type=campo.type)
        except (pa.ArrowInvalid, pa.ArrowTypeError):
            return f"tipo/{campo.name}"

    # pyarrow acepta un datetime sin zona y lo toma como UTC; aquí no.
    if item["capturado_en"].utcoffset() != timedelta(0):
        return "capturado_en_no_utc"
    lista, oferta = item.get("precio_lista"), item.get("precio_oferta")
    if lista is None and oferta is None:
        return "precio_ausente"
    if lista is not None and lista <= 0:
        return "precio_lista_no_positivo"
    if oferta is not None and oferta <= 0:
        return "precio_oferta_no_positivo"
    # Sin descuento, precio_oferta va NULL (el legado copiaba el de lista).
    if lista is not None and oferta is not None and oferta >= lista:
        return "precio_oferta_no_menor"
    if item["moneda"] != "MXN":
        return "moneda"
    if item["tienda"] != tienda:
        return "tienda"
    if item["sku_tienda"].strip().lower() in SKU_CENTINELAS:
        return "sku_centinela"
    imagen = item.get("url_imagen")
    if imagen is not None and not imagen.startswith(("https://", "http://")):
        return "imagen_no_url"
    ean = item.get("ean")
    if ean is not None and not ean.isdigit():
        return "ean_no_digitos"
    if item["escalon"] not in ESCALONES:
        return "escalon"
    if item["contrato_version"] != CONTRATO_VERSION:
        return "contrato_version"
    if not PATRON_CORRIDA.match(item["corrida_id"]):
        return "corrida_id"
    return None


class PipelineContrato:
    """Completa los campos de la corrida, valida y deduplica."""

    def __init__(self, crawler) -> None:
        self.crawler = crawler
        self.vistos: set[tuple[str, str | None]] = set()

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_item(self, item):
        spider = self.crawler.spider
        stats = self.crawler.stats
        datos = ItemAdapter(item).asdict()
        # Campos iguales en toda la corrida: los pone el pipeline para que
        # ningún spider los repita.
        datos.setdefault("contrato_version", CONTRATO_VERSION)
        datos.setdefault("corrida_id", spider.corrida_id)
        datos.setdefault("tienda", spider.name)
        datos.setdefault("escalon", spider.tienda["escalon"])

        regla = validar(datos, spider.name)
        if regla:
            stats.inc_value("contrato/rechazados")
            stats.inc_value(f"contrato/rechazados/{regla}")
            logger.warning("Ítem rechazado por contrato: %s", regla,
                           extra={"url": datos.get("url_producto")})
            # DEBUG: el mensaje "Dropped" de Scrapy imprime el ítem completo.
            raise DropItem(regla, log_level="DEBUG")

        clave = (datos["sku_tienda"], datos.get("zona_precio"))
        if clave in self.vistos:
            stats.inc_value("contrato/duplicados")
            raise DropItem("duplicado", log_level="DEBUG")
        self.vistos.add(clave)
        stats.inc_value("contrato/aceptados")
        return datos
