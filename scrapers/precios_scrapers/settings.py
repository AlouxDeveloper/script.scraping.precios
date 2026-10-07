"""Settings de Scrapy para los spiders de Scrapers 2.0.

Aquí van los defaults comunes. Lo que cambia por entorno sale de variables de
entorno (PRD, sección 3.7) y lo que cambia por tienda (escalón, tráfico) lo
aplica ``SpiderTienda`` desde ``config/tiendas.yml``.
"""
import os

BOT_NAME = "precios_scrapers"
SPIDER_MODULES = ["precios_scrapers.spiders"]
NEWSPIDER_MODULE = "precios_scrapers.spiders"

# Entorno de ejecución. El default es oficina porque hoy todo corre ahí; el
# job de GCP debe declarar "gcp" explícitamente para que los spiders que solo
# se permiten en oficina aborten.
AXIOM_ENTORNO = os.environ.get("AXIOM_ENTORNO", "oficina")
AXIOM_DESTINO = os.environ.get("AXIOM_DESTINO", "./salida/data_v2")
# Carpeta base para pausa y reanudación (JOBDIR); el spider le agrega su slug.
# Vacía no activa JOBDIR: en GCP se reanuda por lotes.
AXIOM_JOBDIR = os.environ.get("AXIOM_JOBDIR", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# Punto de integración del proxy (ADR-07): vacío por defecto.
PROXY_URL = os.environ.get("PROXY_URL", "")

# Escalones a y b. Sin la meta "impersonate", el handler cae al HTTP normal
# de Scrapy (escalón a). El escalón d reemplaza este setting en su spider.
DOWNLOAD_HANDLERS = {
    "http": "scrapy_impersonate.ImpersonateDownloadHandler",
    "https": "scrapy_impersonate.ImpersonateDownloadHandler",
}
DOWNLOADER_MIDDLEWARES = {
    "precios_scrapers.spiders.base.MetaEscalon": 350,
}
# curl_cffi pone el User-Agent y los headers del navegador que impersona. Los
# de Scrapy ("Scrapy/2.19", Accept-Language "en") los pisarían y la huella
# dejaría de parecer Chrome.
USER_AGENT = None
DEFAULT_REQUEST_HEADERS = {}

# robots.txt es un riesgo informado de la ficha, no un filtro: las rutas ya se
# revisaron en el reconocimiento (Metodología, reglas). Además, la petición de
# robots.txt saldría sin impersonar y Akamai la corta.
ROBOTSTXT_OBEY = False

# Tráfico: el spider fija concurrencia, delay y jitter de su tienda;
# AutoThrottle solo puede alargar ese delay.
CONCURRENT_REQUESTS_PER_DOMAIN = 1
AUTOTHROTTLE_ENABLED = True

# Logs JSON de una línea: SpiderTienda instala su propio handler.
LOG_INSTALL_ROOT_HANDLER = False
LOG_LEVEL = "INFO"

# Consolas remotas apagadas: nadie las usa y abren un puerto local.
TELNETCONSOLE_ENABLED = False
REMOTE_CONTROL_ENABLED = False
FEED_EXPORT_ENCODING = "utf-8"
