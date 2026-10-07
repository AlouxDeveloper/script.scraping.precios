"""Pipeline que escribe la corrida en Parquet por lotes y su ``_corrida.json``.

Ruta (PRD, sección 4.6), bajo ``AXIOM_DESTINO`` (carpeta local o
``gs://...``)::

    tienda=<slug>/anio_mes=<AAAA-MM>/corrida=<corrida_id>/parte-NNNN.parquet
                                                         /_corrida.json

Cada ``PARQUET_FILAS_POR_PARTE`` filas se escribe una parte y se reescribe
``_corrida.json`` con estado ``parcial``: si el proceso muere, quedan las
partes escritas, se pierde como máximo un lote y el JSON ya dice ``parcial``.
Al cerrar, el JSON se reescribe con el estado final según la razón de cierre.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow import fs
from scrapy import signals

from precios_scrapers.contrato import CONTRATO_VERSION, ESQUEMA

ZONA_MX = ZoneInfo("America/Mexico_City")
# Razón de cierre que pone el middleware de bloqueo cuando se rinde.
RAZONES_ABORTADA = {"bloqueo_sostenido"}


def estado_por_razon(razon: str) -> str:
    """completa solo si Scrapy terminó la cola; abortada si nos rendimos."""
    if razon == "finished":
        return "completa"
    return "abortada" if razon in RAZONES_ABORTADA else "parcial"


def version_codigo() -> str | None:
    """Sha de git del código; None fuera de un checkout (p. ej. contenedor)."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            check=True, cwd=Path(__file__).parent).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def abrir_destino(destino: str) -> tuple[fs.FileSystem, str]:
    """Filesystem y ruta raíz para una carpeta local o una URI gs://."""
    if "://" not in destino:
        destino = Path(destino).resolve().as_posix()
    return fs.FileSystem.from_uri(destino)


class PipelineParquet:
    """Junta filas validadas y las escribe en partes de tamaño fijo."""

    def __init__(self, crawler) -> None:
        self.crawler = crawler
        self.filas_por_parte = crawler.settings.getint("PARQUET_FILAS_POR_PARTE")
        self.lote: list[dict] = []
        self.partes: list[dict] = []
        self.skus: set[str] = set()
        crawler.signals.connect(self.cerrar, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open_spider(self) -> None:
        spider = self.crawler.spider
        anio_mes = spider.inicio.astimezone(ZONA_MX).strftime("%Y-%m")
        self.fs, raiz = abrir_destino(self.crawler.settings["AXIOM_DESTINO"])
        self.carpeta = (f"{raiz}/tienda={spider.name}/anio_mes={anio_mes}"
                        f"/corrida={spider.corrida_id}")
        # En GCS no hay carpetas; crearlas dejaría objetos vacíos que load/
        # tendría que ignorar.
        if isinstance(self.fs, fs.LocalFileSystem):
            self.fs.create_dir(self.carpeta, recursive=True)

    def process_item(self, item):
        self.lote.append(item)
        self.skus.add(item["sku_tienda"])
        if len(self.lote) >= self.filas_por_parte:
            self.escribir_parte()
            self.escribir_corrida("parcial", razon=None)
        return item

    def escribir_parte(self) -> None:
        tabla = pa.Table.from_pylist(self.lote, schema=ESQUEMA)
        buffer = pa.BufferOutputStream()
        pq.write_table(tabla, buffer)
        datos = buffer.getvalue().to_pybytes()
        nombre = f"parte-{len(self.partes) + 1:04d}.parquet"
        self.escribir(nombre, datos)
        self.partes.append({"nombre": nombre, "filas": tabla.num_rows,
                            "md5": hashlib.md5(datos).hexdigest()})
        self.lote = []

    def escribir(self, nombre: str, datos: bytes) -> None:
        with self.fs.open_output_stream(f"{self.carpeta}/{nombre}") as f:
            f.write(datos)

    def escribir_corrida(self, estado: str, razon: str | None) -> None:
        spider = self.crawler.spider
        stats = self.crawler.stats.get_stats()
        prefijo = "downloader/response_status_count/"
        unicos = len(self.skus)
        total = spider.total_reportado
        corrida = {
            "corrida_id": spider.corrida_id,
            "tienda": spider.name,
            "contrato_version": CONTRATO_VERSION,
            "estado": estado,
            "razon_cierre": razon,
            "inicio": spider.inicio.isoformat(),
            "fin": datetime.now(timezone.utc).isoformat() if razon else None,
            "partes": self.partes,
            "filas_total": sum(p["filas"] for p in self.partes),
            "unicos": unicos,
            "total_reportado": total,
            "cobertura": round(unicos / total, 4) if total else None,
            "peticiones": stats.get("downloader/request_count", 0),
            "respuestas_por_status": {
                clave.removeprefix(prefijo): valor
                for clave, valor in stats.items() if clave.startswith(prefijo)},
            "bloqueos": stats.get("bloqueos", 0),
            "reintentos": stats.get("retry/count", 0),
            "escalon": spider.tienda["escalon"],
            "entorno": self.crawler.settings["AXIOM_ENTORNO"],
            "version_codigo": version_codigo(),
        }
        texto = json.dumps(corrida, ensure_ascii=False, indent=2)
        self.escribir("_corrida.json", texto.encode("utf-8"))

    def cerrar(self, spider, reason: str) -> None:
        # Va en spider_closed y no en close_spider porque solo la señal trae
        # la razón de cierre; las stats siguen abiertas en ese momento.
        if self.lote:
            self.escribir_parte()
        self.escribir_corrida(estado_por_razon(reason), razon=reason)
