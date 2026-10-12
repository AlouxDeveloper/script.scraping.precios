"""Logs de la corrida: legibles en la terminal, JSON para la máquina, alertas.

En oficina, la terminal muestra una línea corta en español por registro y
oculta el ruido de Scrapy, scrapy-playwright y asyncio; todo, ruido incluido,
va además como JSON de una línea a ``AXIOM_LOGS/tienda=<slug>/<corrida>.jsonl``.
En GCP solo sale el JSON, a stderr, porque Cloud Logging lo lee de ahí.

Cada línea JSON lleva ``severity``, ``message``, ``tienda``, ``corrida_id``,
``url``, ``status``, ``escalon`` y ``alerta``. Solo se emiten esos campos y la
hora, nunca los ``extra`` arbitrarios de cada logger, para que un cuerpo de
respuesta no se cuele en el log.

Un registro con ``extra={"alerta": True}`` se manda además a Telegram
(``AlertaTelegram``): así cualquier parte del código avisa en el momento con
solo un log.
"""
import logging
import ssl
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

import truststore
from pythonjsonlogger.json import JsonFormatter

CAMPOS = ["levelname", "message", "tienda", "corrida_id", "url", "status",
          "escalon", "alerta"]
NIVELES = {"DEBUG": "DEBUG", "INFO": "INFO", "WARNING": "AVISO",
           "ERROR": "ERROR", "CRITICAL": "ERROR"}
# De Scrapy, en la terminal solo quedan la línea de avance por minuto y la
# apertura y el cierre del spider; sus volcados de settings y de stats, no.
SCRAPY_VISIBLE = {"scrapy.extensions.logstats", "scrapy.core.engine"}
# scrapy.middleware solo lista los componentes activos y los apagados (el
# "Disabled ... ContextoNavegador" de todo spider que no es escalón d).
# scrapy-playwright avisa "Navigating to ... returned None" en cada página y
# asyncio suelta errores de cierre del ProactorEventLoop en Windows: ninguno
# dice nada útil a quien mira la corrida.
RUIDOSOS = ("scrapy-playwright", "asyncio", "scrapy.middleware", "py.warnings")
# Un mismo aviso no se repite antes de esto (segundos).
REPETICION_ALERTA = 600
ICONOS = {logging.INFO: "✅", logging.WARNING: "🟠", logging.ERROR: "🔴"}

logger = logging.getLogger(__name__)


class ContextoCorrida(logging.Filter):
    """Agrega a cada registro los datos de la corrida y, si hay, la petición."""

    def __init__(self, tienda: str, corrida_id: str, escalon: str) -> None:
        super().__init__()
        self.contexto = {"tienda": tienda, "corrida_id": corrida_id,
                         "escalon": escalon}

    def filter(self, record: logging.LogRecord) -> bool:
        for campo, valor in self.contexto.items():
            setattr(record, campo, valor)
        # El mensaje "Crawled (200) <GET ...>" de Scrapy trae la petición y el
        # status en sus args; así esas líneas llenan url y status sin tocar
        # el LogFormatter.
        args = record.args if isinstance(record.args, dict) else {}
        if not hasattr(record, "url"):
            record.url = getattr(args.get("request"), "url", None)
        if not hasattr(record, "status"):
            record.status = args.get("status")
        if not hasattr(record, "alerta"):
            record.alerta = False
        return True


SIEMPRE = {"severity", "timestamp", "exc_info"}


class FormatoJson(JsonFormatter):
    """JsonFormatter que solo escribe CAMPOS, sin los extra de cada logger.

    Conserva el traceback (``exc_info``): sin él, un "Error downloading" de
    Scrapy no dice qué falló.
    """

    def add_fields(self, log_data, record, message_dict) -> None:
        super().add_fields(log_data, record, message_dict)
        for clave in set(log_data) - set(CAMPOS) - SIEMPRE:
            del log_data[clave]


def formato_json() -> FormatoJson:
    return FormatoJson(CAMPOS, rename_fields={"levelname": "severity"},
                       timestamp=True)


class FormatoTerminal(logging.Formatter):
    """``11:58:13 AVISO Bloqueo (reset) · /farmacia/medicina?start=480``.

    La tienda y la corrida no van en cada línea: las dice una sola vez la
    línea de inicio de ``SpiderTienda``.
    """

    def format(self, record: logging.LogRecord) -> str:
        hora = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        nivel = NIVELES.get(record.levelname, record.levelname)
        texto = f"{hora} {nivel:<5} {record.getMessage()}"
        url = getattr(record, "url", None)
        if url:
            partes = urlparse(url)
            texto += f" · {partes.path}" + (f"?{partes.query}"
                                             if partes.query else "")
        if record.exc_info:
            texto += "\n" + self.formatException(record.exc_info)
        return texto


class SinRuido(logging.Filter):
    """Deja en la terminal solo lo que le sirve a una persona."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(RUIDOSOS):
            return False
        if record.name.startswith("scrapy.") and record.levelno < logging.WARNING:
            return record.name in SCRAPY_VISIBLE
        return True


class AlertaTelegram(logging.Handler):
    """Manda a Telegram los registros marcados con ``alerta``.

    El envío va en un hilo para no frenar la corrida. El hilo no es daemon:
    el aviso de cierre sale justo antes de que termine el proceso, y Python
    espera a los hilos normales antes de salir. Si Telegram falla, solo queda
    un aviso en el log; la corrida sigue.
    """

    def __init__(self, token: str, chat_id: str) -> None:
        super().__init__(logging.INFO)
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
        self.enviados: dict[str, float] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if not getattr(record, "alerta", False):
            return
        mensaje = record.getMessage()
        ahora = time.monotonic()
        if ahora - self.enviados.get(mensaje, -REPETICION_ALERTA) \
                < REPETICION_ALERTA:
            return
        self.enviados[mensaje] = ahora
        icono = ICONOS.get(min(record.levelno, logging.ERROR), "🔴")
        texto = (f"{icono} {getattr(record, 'tienda', '?')} · "
                 f"{getattr(record, 'corrida_id', '?')}\n{mensaje}")
        if getattr(record, "url", None):
            texto += f"\n{record.url}"
        threading.Thread(target=self.enviar, args=(texto,)).start()

    def enviar(self, texto: str) -> None:
        datos = urlencode({"chat_id": self.chat_id, "text": texto}).encode()
        try:
            # Con los certificados del sistema y no los de Python: en redes
            # que inspeccionan HTTPS (proxy o antivirus con su propia CA), la
            # cadena trae un certificado que solo Windows conoce y urllib
            # fallaba con CERTIFICATE_VERIFY_FAILED.
            contexto = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            with urlopen(self.url, data=datos, timeout=10, context=contexto):
                pass
        except Exception as error:  # noqa: BLE001 -- nunca tumba la corrida
            # La causa (DNS, certificado, proxy) dice qué arreglar en la PC;
            # el token del bot va en la URL, así que se tapa por si aparece.
            token = self.url.split("/bot")[1].split("/")[0]
            causa = str(getattr(error, "reason", error)).replace(token, "***")
            logger.warning("No se pudo enviar la alerta a Telegram: %s (%s)",
                           type(error).__name__, causa)


def instalar(nivel: str, contexto: ContextoCorrida, settings) -> Path | None:
    """Reemplaza los handlers del logger raíz según el entorno.

    Devuelve la ruta del archivo JSON, o None si no se escribe (GCP o sin
    ``AXIOM_LOGS``, como en las pruebas).
    """
    handlers: list[logging.Handler] = []
    archivo = None
    if settings.get("AXIOM_ENTORNO") == "gcp":
        json_stderr = logging.StreamHandler()
        json_stderr.setFormatter(formato_json())
        handlers.append(json_stderr)
    else:
        # En Windows, con la salida redirigida a un pipe o a un archivo,
        # Python escribe en cp1252 y Git Bash muestra "·" y los acentos
        # como "�"; en UTF-8 se leen bien en ambos casos.
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        terminal = logging.StreamHandler()
        terminal.addFilter(contexto)
        terminal.addFilter(SinRuido())
        terminal.setFormatter(FormatoTerminal())
        handlers.append(terminal)
        if settings.get("AXIOM_LOGS"):
            c = contexto.contexto
            archivo = (Path(settings["AXIOM_LOGS"]) / f"tienda={c['tienda']}"
                       / f"{c['corrida_id']}.jsonl")
            archivo.parent.mkdir(parents=True, exist_ok=True)
            json_archivo = logging.FileHandler(archivo, encoding="utf-8")
            json_archivo.setFormatter(formato_json())
            handlers.append(json_archivo)
    if settings.get("TELEGRAM_BOT_TOKEN") and settings.get("TELEGRAM_CHAT_ID"):
        handlers.append(AlertaTelegram(settings["TELEGRAM_BOT_TOKEN"],
                                       settings["TELEGRAM_CHAT_ID"]))
    raiz = logging.getLogger()
    for viejo in list(raiz.handlers):
        raiz.removeHandler(viejo)
    raiz.setLevel(logging.NOTSET)
    for handler in handlers:
        if handler.level == logging.NOTSET:
            handler.setLevel(nivel)
        if contexto not in handler.filters:
            handler.addFilter(contexto)
        raiz.addHandler(handler)
    return archivo
