"""Pruebas de las alertas de corrida y de las dos salidas de log (ALD-129)."""
import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pyarrow import fs as pafs
from scrapy.settings import Settings

from precios_scrapers import alertas, logs

SANA = {"corrida_id": "walmart_20261008T1700Z", "tienda": "walmart",
        "estado": "completa", "razon_cierre": "finished",
        "inicio": "2026-10-08T17:00:00+00:00",
        "fin": "2026-10-08T17:40:00+00:00", "filas_total": 2341,
        "unicos": 2341, "total_reportado": 2384, "cobertura": 0.982}


@pytest.fixture
def settings():
    proyecto = Settings()
    proyecto.setmodule("precios_scrapers.settings")
    return proyecto


def test_corrida_sana_no_alerta(settings):
    assert alertas.revisar(SANA, SANA, 0, settings) == []


def test_reglas_de_cierre(settings):
    mala = {**SANA, "estado": "parcial", "razon_cierre": "sucursal_cambiada",
            "unicos": 1376, "filas_total": 1376, "cobertura": 0.577,
            "fin": "2026-10-10T00:00:00+00:00"}
    razones = alertas.revisar(mala, SANA, 20, settings)
    assert razones[0] == "Corrida parcial por sucursal_cambiada"
    assert razones[1].startswith("Cobertura 57.7% (mínimo 98%)")
    assert razones[2].startswith("Productos únicos cayeron 41.2%")
    assert razones[3].startswith("1.4% de filas rechazadas")
    assert razones[4] == "La corrida duró 31.0 h"


def test_pocos_rechazos_en_corrida_chica_no_alertan(settings):
    chica = {**SANA, "filas_total": 50, "unicos": 50, "total_reportado": 50,
             "cobertura": 1.0}
    assert alertas.revisar(chica, None, 3, settings) == []


def escribir_corrida(raiz, anio_mes, corrida_id, estado, unicos):
    carpeta = raiz / "tienda=walmart" / f"anio_mes={anio_mes}" / \
        f"corrida={corrida_id}"
    carpeta.mkdir(parents=True)
    (carpeta / "_corrida.json").write_text(json.dumps(
        {"corrida_id": corrida_id, "estado": estado, "unicos": unicos}))


def test_corrida_anterior_es_la_ultima_completa(tmp_path):
    escribir_corrida(tmp_path, "2026-09", "walmart_20260930T0100Z",
                     "completa", 1)
    escribir_corrida(tmp_path, "2026-10", "walmart_20261007T0100Z",
                     "completa", 2)
    escribir_corrida(tmp_path, "2026-10", "walmart_20261008T0100Z",
                     "parcial", 3)
    escribir_corrida(tmp_path, "2026-10", "walmart_20261009T0100Z",
                     "completa", 4)
    anterior = alertas.corrida_anterior(
        pafs.LocalFileSystem(), tmp_path.as_posix(), "walmart",
        "walmart_20261009T0100Z")
    assert anterior["unicos"] == 2
    # Al revisar una corrida vieja, una más nueva no cuenta como anterior.
    assert alertas.corrida_anterior(
        pafs.LocalFileSystem(), tmp_path.as_posix(), "walmart",
        "walmart_20261007T0100Z")["unicos"] == 1
    assert alertas.corrida_anterior(pafs.LocalFileSystem(),
                                    tmp_path.as_posix(), "aurrera", "x") \
        is None


class Stats(dict):
    def get_value(self, clave, defecto=None):
        return self.get(clave, defecto)


def vigia(settings, horas=0.0):
    crawler = SimpleNamespace(
        settings=settings, stats=Stats(),
        signals=SimpleNamespace(connect=lambda *a, **k: None),
        spider=SimpleNamespace(inicio=datetime.now(timezone.utc)
                               - timedelta(hours=horas)))
    revisor = alertas.Vigia(crawler)
    revisor.respuestas, revisor.desde = 0, 0.0
    return revisor


def alertas_emitidas(caplog):
    return [r.getMessage() for r in caplog.records
            if getattr(r, "alerta", False)]


def test_vigia_sin_avance_avisa_una_vez_por_atasco(settings, caplog):
    revisor = vigia(settings)
    revisor.reloj = lambda: 21 * 60
    revisor.revisar()
    revisor.revisar()
    assert len(alertas_emitidas(caplog)) == 1
    assert alertas_emitidas(caplog)[0].startswith("Sin avance: 21 min")
    # Vuelve a avanzar y se atora otra vez: nuevo aviso.
    revisor.crawler.stats["response_received_count"] = 5
    revisor.revisar()
    revisor.reloj = lambda: 42 * 60
    revisor.revisar()
    assert len(alertas_emitidas(caplog)) == 2


def test_vigia_rechazos_y_horas(settings, caplog):
    revisor = vigia(settings, horas=31)
    revisor.crawler.stats.update({"response_received_count": 1,
                                  "contrato/rechazados": 10,
                                  "contrato/aceptados": 990})
    revisor.revisar()
    assert alertas_emitidas(caplog) == [
        "1.0% de filas rechazadas por el contrato (10 de 1000)",
        "La corrida lleva 31.0 h"]


def registro(mensaje, nivel=logging.ERROR, nombre="precios", **extra):
    record = logging.LogRecord(nombre, nivel, __file__, 1, mensaje, None,
                               None)
    record.__dict__.update(extra)
    logs.ContextoCorrida("guadalajara", "guadalajara_20261008T1751Z",
                         "b").filter(record)
    return record


def test_telegram_manda_solo_alertas_y_no_repite(monkeypatch):
    enviados = []
    handler = logs.AlertaTelegram("TOKEN", "123")
    monkeypatch.setattr(handler, "enviar", enviados.append)
    monkeypatch.setattr(logs.threading, "Thread", lambda target, args:
                        SimpleNamespace(start=lambda: target(*args)))
    handler.emit(registro("Bloqueo (reset), 1 seguidos"))
    handler.emit(registro("Pausa de 30 min", alerta=True,
                          url="https://x.mx/a"))
    handler.emit(registro("Pausa de 30 min", alerta=True,
                          url="https://x.mx/a"))
    assert enviados == ["🔴 guadalajara · guadalajara_20261008T1751Z\n"
                        "Pausa de 30 min\nhttps://x.mx/a"]


def test_telegram_caido_no_rompe_la_corrida(monkeypatch, caplog):
    def falla(*args, **kwargs):
        raise OSError("sin red")
    monkeypatch.setattr(logs, "urlopen", falla)
    logs.AlertaTelegram("TOKEN", "123").enviar("hola")
    assert "No se pudo enviar la alerta a Telegram: OSError" in caplog.text
    assert "TOKEN" not in caplog.text


def test_terminal_legible_y_sin_ruido():
    linea = logs.FormatoTerminal().format(registro(
        "Bloqueo (reset), 1 seguidos", logging.WARNING,
        url="https://www.farmaciasguadalajara.com/farmacia/medicina"
            "?start=480&sz=96"))
    assert linea.endswith(" AVISO Bloqueo (reset), 1 seguidos · "
                          "/farmacia/medicina?start=480&sz=96")
    filtro = logs.SinRuido()
    assert not filtro.filter(registro("Navigating to", logging.WARNING,
                                      "scrapy-playwright"))
    assert not filtro.filter(registro("Enabled extensions", logging.INFO,
                                      "scrapy.middleware"))
    assert filtro.filter(registro("Crawled 9 pages", logging.INFO,
                                  "scrapy.extensions.logstats"))
    assert filtro.filter(registro("Error downloading", logging.ERROR,
                                  "scrapy.core.scraper"))


def test_json_a_archivo_por_corrida(tmp_path):
    contexto = logs.ContextoCorrida("walmart", "walmart_20261008T1700Z", "d")
    archivo = logs.instalar("INFO", contexto, {"AXIOM_ENTORNO": "oficina",
                                               "AXIOM_LOGS": str(tmp_path)})
    logging.getLogger("scrapy-playwright").warning("Navigating to x")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert archivo == (tmp_path / "tienda=walmart"
                       / "walmart_20261008T1700Z.jsonl")
    linea = json.loads(archivo.read_text().splitlines()[-1])
    assert linea["message"] == "Navigating to x"
    assert linea["corrida_id"] == "walmart_20261008T1700Z"
    assert linea["alerta"] is False
