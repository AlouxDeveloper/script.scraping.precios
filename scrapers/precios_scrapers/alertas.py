"""Alertas de corrida por Telegram (ALD-129, PRD sección 5.3).

Todas las alertas son logs con ``extra={"alerta": True}``; ``logs.AlertaTelegram``
las manda. Aquí viven las reglas:

- ``Vigia``: extensión de Scrapy que cada ``ALERTA_INTERVALO_S`` revisa la
  corrida en vivo: sin respuestas nuevas en ``ALERTA_SIN_AVANCE_MIN``,
  rechazos del contrato sobre ``ALERTA_RECHAZO_MAX`` y más de
  ``ALERTA_HORAS_MAX`` horas. Cada regla avisa una vez por corrida (sin
  avance, una vez por cada atasco).
- ``al_cerrar``: la llama ``PipelineParquet`` con el ``_corrida.json`` final;
  avisa si la corrida no quedó completa, si la cobertura queda bajo
  ``ALERTA_COBERTURA_MIN`` o si los únicos caen más de ``ALERTA_CAIDA_MAX``
  contra la última corrida completa. Si todo salió bien, avisa el fin.

El bloqueo sostenido avisa desde ``middlewares/bloqueo.py`` al entrar en la
pausa larga; su cierre llega por ``al_cerrar``.

Uso para revisar a mano un ``_corrida.json`` (y mandar sus alertas), desde la
raíz del repo:
    uv run --project scrapers python -m precios_scrapers.alertas \\
        salida/data_v2/tienda=.../corrida=.../_corrida.json
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pyarrow import fs as pafs
from scrapy import signals

logger = logging.getLogger(__name__)
ALERTA = {"alerta": True}


def duracion_horas(corrida: dict) -> float | None:
    if not corrida.get("fin"):
        return None
    inicio = datetime.fromisoformat(corrida["inicio"])
    return (datetime.fromisoformat(corrida["fin"]) - inicio).total_seconds() / 3600


def revisar(corrida: dict, anterior: dict | None, rechazados: int,
            settings) -> list[str]:
    """Razones para alertar sobre una corrida cerrada; vacía si salió bien."""
    razones = []
    if corrida["estado"] != "completa":
        razones.append(f"Corrida {corrida['estado']} por "
                       f"{corrida['razon_cierre']}")
    cobertura = corrida.get("cobertura")
    minimo = settings.getfloat("ALERTA_COBERTURA_MIN")
    if cobertura is not None and cobertura < minimo:
        razones.append(f"Cobertura {cobertura:.1%} (mínimo {minimo:.0%}): "
                       f"{corrida['unicos']:,} de {corrida['total_reportado']:,}")
    if anterior and anterior.get("unicos"):
        caida = 1 - corrida["unicos"] / anterior["unicos"]
        if caida > settings.getfloat("ALERTA_CAIDA_MAX"):
            razones.append(f"Productos únicos cayeron {caida:.1%}: "
                           f"{corrida['unicos']:,} contra {anterior['unicos']:,}"
                           f" de {anterior['corrida_id']}")
    filas = corrida["filas_total"] + rechazados
    if (filas and filas >= settings.getint("ALERTA_RECHAZO_MIN_FILAS")
            and rechazados / filas > settings.getfloat("ALERTA_RECHAZO_MAX")):
        razones.append(f"{rechazados / filas:.1%} de filas rechazadas por el "
                       f"contrato ({rechazados:,})")
    horas = duracion_horas(corrida)
    if horas is not None and horas > settings.getfloat("ALERTA_HORAS_MAX"):
        razones.append(f"La corrida duró {horas:.1f} h")
    return razones


def corrida_anterior(sistema: pafs.FileSystem, raiz: str, tienda: str,
                     actual: str) -> dict | None:
    """El ``_corrida.json`` de la última corrida completa antes de ``actual``.

    Las rutas ``anio_mes=AAAA-MM/corrida=<slug>_AAAAMMDDTHHMMZ`` ordenan por
    fecha como texto, así que basta recorrerlas de la más nueva a la más
    vieja. Sirve igual en local y en GCS.
    """
    selector = pafs.FileSelector(f"{raiz}/tienda={tienda}", recursive=True,
                                 allow_not_found=True)
    rutas = sorted((info.path for info in sistema.get_file_info(selector)
                    if info.path.endswith("/_corrida.json")
                    and info.path.split("/corrida=")[-1] < f"{actual}/"),
                   reverse=True)
    for ruta in rutas:
        with sistema.open_input_stream(ruta) as f:
            corrida = json.loads(f.read())
        if corrida.get("estado") == "completa":
            return corrida
    return None


def al_cerrar(crawler, corrida: dict, sistema: pafs.FileSystem,
              raiz: str) -> None:
    """Alerta con las razones de ``revisar`` o avisa que todo salió bien."""
    try:
        anterior = corrida_anterior(sistema, raiz, corrida["tienda"],
                                    corrida["corrida_id"])
    except OSError:
        # Sin la anterior solo se pierde la regla de caída; las demás siguen.
        logger.warning("No se pudo leer la corrida anterior", exc_info=True)
        anterior = None
    rechazados = crawler.stats.get_value("contrato/rechazados", 0)
    razones = revisar(corrida, anterior, rechazados, crawler.settings)
    if razones:
        logger.error("\n".join(razones), extra=ALERTA)
        return
    cobertura = corrida.get("cobertura")
    logger.info("Corrida completa: %s únicos, cobertura %s, %.1f h",
                f"{corrida['unicos']:,}",
                f"{cobertura:.1%}" if cobertura is not None else "sin total",
                duracion_horas(corrida) or 0, extra=ALERTA)


class Vigia:
    """Revisa la corrida en vivo cada ``ALERTA_INTERVALO_S`` segundos."""

    def __init__(self, crawler) -> None:
        self.crawler = crawler
        self.settings = crawler.settings
        self.reloj = time.monotonic
        self.tarea = None
        self.avisadas: set[str] = set()
        crawler.signals.connect(self.abrir, signal=signals.spider_opened)
        crawler.signals.connect(self.cerrar, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def abrir(self, spider) -> None:
        # Import local: importar task al cargar el módulo instalaría el
        # reactor por defecto antes que el de asyncio.
        from twisted.internet import task

        self.respuestas = 0
        self.desde = self.reloj()
        self.tarea = task.LoopingCall(self.revisar)
        self.tarea.start(self.settings.getint("ALERTA_INTERVALO_S"),
                         now=False)

    def cerrar(self, spider) -> None:
        if self.tarea is not None and self.tarea.running:
            self.tarea.stop()

    def avisar(self, regla: str, mensaje: str, *args) -> None:
        if regla not in self.avisadas:
            self.avisadas.add(regla)
            logger.error(mensaje, *args, extra=ALERTA)

    def revisar(self) -> None:
        stats = self.crawler.stats
        ahora = self.reloj()
        # Avance = respuestas descargadas. Los productos no sirven: hay tramos
        # largos de puros duplicados (Walmart, segmentos de una hoja grande).
        respuestas = stats.get_value("response_received_count", 0)
        if respuestas != self.respuestas:
            self.respuestas, self.desde = respuestas, ahora
            self.avisadas.discard("sin_avance")
        minutos = (ahora - self.desde) / 60
        if minutos >= self.settings.getint("ALERTA_SIN_AVANCE_MIN"):
            self.avisar("sin_avance", "Sin avance: %d min sin respuestas "
                        "nuevas (%s descargadas)", minutos, respuestas)

        rechazados = stats.get_value("contrato/rechazados", 0)
        filas = (rechazados + stats.get_value("contrato/aceptados", 0)
                 + stats.get_value("contrato/duplicados", 0))
        if (filas and filas >= self.settings.getint("ALERTA_RECHAZO_MIN_FILAS")
                and rechazados / filas
                > self.settings.getfloat("ALERTA_RECHAZO_MAX")):
            self.avisar("rechazos", "%.1f%% de filas rechazadas por el "
                        "contrato (%s de %s)", 100 * rechazados / filas,
                        rechazados, filas)

        inicio = self.crawler.spider.inicio
        horas = (datetime.now(timezone.utc) - inicio).total_seconds() / 3600
        if horas > self.settings.getfloat("ALERTA_HORAS_MAX"):
            self.avisar("horas", "La corrida lleva %.1f h", horas)


if __name__ == "__main__":
    # Revisión a mano de un _corrida.json: carga los settings del proyecto
    # (y con ellos el .env) y manda las alertas como lo haría la corrida.
    import os
    from types import SimpleNamespace

    from scrapy.utils.project import get_project_settings

    from precios_scrapers import logs

    os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "precios_scrapers.settings")
    ruta = Path(sys.argv[1]).resolve()
    corrida = json.loads(ruta.read_text(encoding="utf-8"))
    settings = get_project_settings()
    logs.instalar("INFO", logs.ContextoCorrida(
        corrida["tienda"], corrida["corrida_id"], corrida["escalon"]),
        {**settings.copy_to_dict(), "AXIOM_LOGS": ""})
    # Fuera de la corrida no hay stats: los rechazos no se conocen.
    crawler = SimpleNamespace(settings=settings, stats=SimpleNamespace(
        get_value=lambda clave, defecto=None: defecto))
    raiz_tienda = next(p for p in ruta.parents
                       if p.name.startswith("tienda="))
    al_cerrar(crawler, corrida, pafs.LocalFileSystem(),
              raiz_tienda.parent.as_posix())
