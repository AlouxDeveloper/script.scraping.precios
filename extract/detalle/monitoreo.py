"""Monitoreo de corridas de scraping en extract/detalle.

Log a archivo, detección heurística de bloqueo/captcha en el HTML de la
página y alerta por Telegram cuando los fallos se repiten. Módulo aparte de
cualquier scraper puntual para que siga sirviendo si se reescriben los
scripts de esta carpeta.

Variables de entorno para la alerta (si faltan, se omite en silencio). Se
leen de un .env en la raíz del repo (ver .env.example) o del entorno real:
    TELEGRAM_BOT_TOKEN  -- token del bot, dado por @BotFather
    TELEGRAM_CHAT_ID    -- id del chat/usuario al que se envía la alerta

Uso típico dentro de un scraper:

    from monitoreo import MonitorFallos, configurar_logger, es_pagina_bloqueada

    logger = configurar_logger("walmart")
    monitor = MonitorFallos(tienda="walmart", logger=logger)
    ...
    driver.get(url)
    if es_pagina_bloqueada(driver.page_source):
        monitor.registrar_fallo("bloqueo_detectado")
        continue
    ...
    monitor.registrar_exito()
"""
import logging
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DIR_LOGS = Path("./salida/logs")

UMBRAL_FALLOS_DEFECTO = 8
PAUSA_SEGUNDOS_DEFECTO = 600

# Señales de bloqueo/captcha vistas en sitios VTEX y afines. No es un parser
# de la página, solo un vistazo rápido al HTML crudo antes de seguir.
PATRONES_BLOQUEO = [
    re.compile(r"captcha", re.IGNORECASE),
    re.compile(r"verifica que (eres|no eres) (humano|un robot)", re.IGNORECASE),
    re.compile(r"unusual traffic", re.IGNORECASE),
    re.compile(r"acceso denegado", re.IGNORECASE),
    re.compile(r"access denied", re.IGNORECASE),
    re.compile(r"\b403 forbidden\b", re.IGNORECASE),
    re.compile(r"robot check", re.IGNORECASE),
]


def es_pagina_bloqueada(html: str) -> bool:
    """Revisa si el HTML trae alguna señal conocida de bloqueo o captcha."""
    if not html:
        return False
    return any(patron.search(html) for patron in PATRONES_BLOQUEO)


def configurar_logger(tienda: str) -> logging.Logger:
    """Crea/reutiliza un logger que escribe en ./salida/logs/<tienda>.log.

    Queda en archivo, no solo en consola, para poder revisar una corrida
    después aunque la sesión remota ya se haya cerrado.
    """
    DIR_LOGS.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"monitoreo.{tienda}")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        manejador = logging.FileHandler(
            DIR_LOGS / f"{tienda}.log", encoding="utf-8"
        )
        manejador.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(manejador)
    return logger


def enviar_alerta_telegram(mensaje: str) -> None:
    """Envía `mensaje` al bot de Telegram configurado por variables de entorno.

    Silencioso ante cualquier falla (sin credenciales, sin red, timeout): una
    alerta que no llega nunca debe tumbar la corrida de scraping.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": mensaje},
            timeout=10,
        )
    except requests.RequestException:
        pass


class MonitorFallos:
    """Cuenta fallos consecutivos de una tienda y reacciona al cruzar un umbral.

    Un fallo suelto (timeout de red, elemento tardío) no amerita nada; una
    racha larga sí es señal de bloqueo o captcha real. El contador se
    resetea en cada éxito para no arrastrar fallos de otra parte de la
    corrida. Al cruzar el umbral: alerta por Telegram y pausa la corrida
    `pausa_segundos` (en vez de seguir "a ciegas" gastando el resto de la
    lista contra un bloqueo activo); al reanudar, el contador vuelve a
    empezar en cero -- si el bloqueo sigue, vuelve a pausar más adelante.
    """

    def __init__(self, tienda: str, logger: logging.Logger,
                 umbral: int = UMBRAL_FALLOS_DEFECTO,
                 pausa_segundos: int = PAUSA_SEGUNDOS_DEFECTO):
        self.tienda = tienda
        self.logger = logger
        self.umbral = umbral
        self.pausa_segundos = pausa_segundos
        self.fallos_consecutivos = 0
        self.exitos = 0

    def registrar_exito(self) -> None:
        """Marca un producto capturado bien y resetea la racha de fallos."""
        self.exitos += 1
        self.fallos_consecutivos = 0

    def registrar_fallo(self, motivo: str) -> None:
        """Marca un fallo; al cruzar el umbral alerta y pausa la corrida."""
        self.fallos_consecutivos += 1
        self.logger.warning(
            "Fallo #%s consecutivo (%s): %s",
            self.fallos_consecutivos, self.tienda, motivo,
        )
        if self.fallos_consecutivos >= self.umbral:
            minutos = self.pausa_segundos // 60
            mensaje = (
                f"⚠️ {self.tienda}: {self.fallos_consecutivos} fallos "
                f"seguidos ({motivo}). Pausando {minutos} min por posible "
                "bloqueo o captcha."
            )
            self.logger.error(mensaje)
            enviar_alerta_telegram(mensaje)
            time.sleep(self.pausa_segundos)
            self.fallos_consecutivos = 0
