"""Logs JSON de una línea para Cloud Logging y para la consola de oficina.

Cada línea lleva ``severity``, ``message``, ``tienda``, ``corrida_id``,
``url``, ``status`` y ``escalon``. Solo se emiten esos campos y la hora, nunca
los ``extra`` arbitrarios de cada logger, para que un cuerpo de respuesta no
se cuele en el log.
"""
import logging

from pythonjsonlogger.json import JsonFormatter

CAMPOS = ["levelname", "message", "tienda", "corrida_id", "url", "status",
          "escalon"]


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


def instalar(nivel: str, contexto: ContextoCorrida) -> None:
    """Reemplaza los handlers del logger raíz por uno JSON en stderr."""
    handler = logging.StreamHandler()
    handler.setLevel(nivel)
    handler.addFilter(contexto)
    handler.setFormatter(FormatoJson(
        CAMPOS, rename_fields={"levelname": "severity"}, timestamp=True))
    raiz = logging.getLogger()
    for viejo in list(raiz.handlers):
        raiz.removeHandler(viejo)
    raiz.setLevel(logging.NOTSET)
    raiz.addHandler(handler)
