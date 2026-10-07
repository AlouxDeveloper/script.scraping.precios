"""Spider base de Scrapers 2.0: configuración por tienda y por entorno.

Cada spider de tienda hereda de ``SpiderTienda`` y declara ``name`` igual a su
slug en ``config/tiendas.yml``. La base lee ese bloque, aplica el tráfico de
la tienda, instala los logs JSON y aborta al inicio si el entorno
(``AXIOM_ENTORNO``) no está en ``entornos_permitidos``: así se implementa el
modelo híbrido sin ramas de código (PRD, sección 3.7).
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

import scrapy
import yaml

from precios_scrapers import logs

RUTA_TIENDAS = Path(__file__).resolve().parents[2] / "config" / "tiendas.yml"
# Perfil de curl_cffi por escalón. El escalón a va sin impersonar (HTTP de
# Scrapy); el c usa el perfil para su parte HTTP y el d no pasa por curl_cffi.
PERFIL_POR_ESCALON = {"a": None, "b": "chrome", "c": "chrome", "d": None}

logger = logging.getLogger(__name__)


class EntornoNoPermitido(RuntimeError):
    """La tienda no se puede correr en el entorno actual."""


def cargar_tienda(slug: str) -> dict:
    """Devuelve el bloque de ``slug`` en tiendas.yml o falla con su nombre."""
    with RUTA_TIENDAS.open(encoding="utf-8") as f:
        tiendas = yaml.safe_load(f)
    if slug not in tiendas:
        raise KeyError(f"La tienda '{slug}' no está en {RUTA_TIENDAS}")
    return tiendas[slug]


class SpiderTienda(scrapy.Spider):
    """Spider con la configuración de su tienda en ``self.tienda``."""

    @classmethod
    def update_settings(cls, settings) -> None:
        trafico = cargar_tienda(cls.name)["trafico"]
        settings.set("CONCURRENT_REQUESTS_PER_DOMAIN", trafico["concurrencia"],
                     priority="spider")
        settings.set("DOWNLOAD_DELAY", trafico["delay"], priority="spider")
        settings.set("DOWNLOAD_DELAY_JITTER", trafico["jitter"],
                     priority="spider")
        if settings.get("AXIOM_JOBDIR"):
            settings.set("JOBDIR", str(Path(settings["AXIOM_JOBDIR"]) / cls.name),
                         priority="spider")
        # Al final, para que custom_settings de la subclase gane sobre el yml.
        super().update_settings(settings)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        # TODO: con JOBDIR, la corrida reanudada debe conservar su corrida_id
        # (guardarlo en spider.state); lo resuelve el pipeline de _corrida.json.
        spider.corrida_id = (
            f"{cls.name}_{datetime.now(timezone.utc):%Y%m%dT%H%MZ}")
        logs.instalar(crawler.settings.get("LOG_LEVEL"), logs.ContextoCorrida(
            cls.name, spider.corrida_id, spider.tienda["escalon"]))
        entorno = crawler.settings.get("AXIOM_ENTORNO")
        permitidos = spider.tienda["entornos_permitidos"]
        if entorno not in permitidos:
            mensaje = (f"La tienda '{cls.name}' no puede correr en el entorno "
                       f"'{entorno}'; permitidos: {permitidos}")
            logger.error(mensaje)
            raise EntornoNoPermitido(mensaje)
        return spider

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tienda = cargar_tienda(self.name)
        self.impersonate = PERFIL_POR_ESCALON[self.tienda["escalon"]]


class MetaEscalon:
    """Pone la meta ``impersonate`` del spider en cada petición.

    Va como middleware y no en el spider para cubrir también las peticiones
    que arma Scrapy o ``response.follow``. Respeta la meta si ya viene.
    """

    def __init__(self, crawler) -> None:
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        perfil = getattr(self.crawler.spider, "impersonate", None)
        if perfil:
            request.meta.setdefault("impersonate", perfil)
