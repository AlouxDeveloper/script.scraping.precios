"""Configuración de Google Cloud, tipada y validada al arrancar.

El objetivo es que un error de configuración se vea en la primera línea de
salida, nombrando el campo y el archivo, en vez de reventar como un `KeyError`
a mitad de una subida de 385 MB.
"""

import os
import re
from dataclasses import dataclass, fields

import yaml

from precios_load.rutas import raiz_repo

# Ruta del YAML, relativa a la raíz del repo.
RUTA_GCP_YML = "load/config/gcp.yml"

# Ubicaciones válidas para el par bucket + dataset. Se restringe a propósito:
# un typo aquí ("us" en vez de "US", "USA") produce errores confusos de
# BigQuery mucho más tarde.
UBICACIONES = ("US", "EU")

# Formato del corte de mes: `2026-08`.
FORMATO_ANIO_MES = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


class ErrorConfig(Exception):
    """Configuración inválida. Siempre nombra el campo y el archivo."""


@dataclass(frozen=True)
class ConfigGCP:
    """Todo lo que el pipeline necesita saber de la infraestructura."""

    project_id: str
    location: str
    bucket_raw: str
    bucket_bronce: str
    prefijo: str
    dataset_bronce: str
    dataset_silver: str
    dataset_ops: str
    conexion_biglake: str
    ruta_local_datos: str
    anio_mes_maximo: str

    # --- Rutas derivadas -------------------------------------------------

    def uri_raw(self, tienda: str, anio_mes: str, nombre_archivo: str) -> str:
        """URI del CSV original en la capa raw."""
        return (
            f"gs://{self.bucket_raw}/{self.prefijo}"
            f"/tienda={tienda}/anio_mes={anio_mes}/{nombre_archivo}"
        )

    def uri_bronce(self, tienda: str, anio_mes: str, nombre_archivo: str) -> str:
        """URI del Parquet en la capa bronce."""
        return (
            f"gs://{self.bucket_bronce}/{self.prefijo}"
            f"/tienda={tienda}/anio_mes={anio_mes}/{nombre_archivo}"
        )

    def prefijo_raw(self) -> str:
        """Prefijo común de la capa raw, antes de las particiones hive."""
        return f"gs://{self.bucket_raw}/{self.prefijo}"

    def prefijo_bronce(self) -> str:
        """Prefijo que consume el hive partitioning de la external table."""
        return f"gs://{self.bucket_bronce}/{self.prefijo}"

    def tabla_bronce(self, nombre: str) -> str:
        """Referencia completa a una tabla del dataset de bronce (external tables)."""
        return f"{self.project_id}.{self.dataset_bronce}.{nombre}"

    def tabla_silver(self, nombre: str) -> str:
        """Referencia completa a una tabla del dataset de silver (nativas, limpias)."""
        return f"{self.project_id}.{self.dataset_silver}.{nombre}"

    def tabla_ops(self, nombre: str) -> str:
        """Referencia completa a una tabla del dataset de operación (manifest, vistas)."""
        return f"{self.project_id}.{self.dataset_ops}.{nombre}"

    def conexion(self) -> str:
        """Referencia completa a la conexión BigLake."""
        return f"{self.project_id}.{self.location.lower()}.{self.conexion_biglake}"

    def ruta_datos(self) -> str:
        """Ruta absoluta a `salida/data`, resuelta desde la raíz del repo."""
        return os.path.normpath(os.path.join(raiz_repo(), self.ruta_local_datos))


def cargar_config(ruta_yml: str = RUTA_GCP_YML) -> ConfigGCP:
    """Lee el YAML, valida y devuelve la configuración.

    Se llama una sola vez al inicio de cada comando, antes de abrir ninguna
    conexión y antes de recorrer `salida/data`.
    """
    ruta = os.path.join(raiz_repo(), ruta_yml)

    if not os.path.exists(ruta):
        raise ErrorConfig(f"No se encontró el archivo de configuración: {ruta_yml}")

    with open(ruta, encoding="utf-8") as f:
        crudo = yaml.safe_load(f)

    if not isinstance(crudo, dict):
        raise ErrorConfig(f"{ruta_yml}: se esperaba un mapeo de claves, se leyó {type(crudo).__name__}")

    esperadas = {campo.name for campo in fields(ConfigGCP)}

    faltantes = sorted(esperadas - set(crudo))
    if faltantes:
        raise ErrorConfig(f"{ruta_yml}: falta el campo '{faltantes[0]}'" + _y_ademas(faltantes))

    sobrantes = sorted(set(crudo) - esperadas)
    if sobrantes:
        raise ErrorConfig(
            f"{ruta_yml}: campo desconocido '{sobrantes[0]}'" + _y_ademas(sobrantes)
        )

    for clave in sorted(esperadas):
        valor = crudo[clave]
        if not isinstance(valor, str):
            tipo = "vacío" if valor is None else f"un {type(valor).__name__}"
            raise ErrorConfig(f"{ruta_yml}: el campo '{clave}' está {tipo}, se esperaba texto")
        if not valor.strip():
            raise ErrorConfig(f"{ruta_yml}: el campo '{clave}' está vacío")

    config = ConfigGCP(**{clave: crudo[clave].strip() for clave in esperadas})
    _validar_valores(config, ruta_yml)
    return config


def _y_ademas(nombres: list[str]) -> str:
    """Sufijo que menciona cuántos campos más hay en la misma condición."""
    return "" if len(nombres) == 1 else f" (y {len(nombres) - 1} más: {', '.join(nombres[1:])})"


def _validar_valores(config: ConfigGCP, ruta_yml: str) -> None:
    """Reglas que no se ven en el tipo pero rompen más adelante."""
    if config.location not in UBICACIONES:
        raise ErrorConfig(
            f"{ruta_yml}: el campo 'location' vale '{config.location}', "
            f"se esperaba una de {', '.join(UBICACIONES)}"
        )

    # Error clásico: pegar la URI completa en un campo que espera solo el nombre.
    for clave in ("bucket_raw", "bucket_bronce"):
        valor = getattr(config, clave)
        if valor.startswith("gs://") or "/" in valor:
            raise ErrorConfig(
                f"{ruta_yml}: el campo '{clave}' debe ser solo el nombre del bucket, "
                f"sin 'gs://' ni rutas; se leyó '{valor}'"
            )

    if not FORMATO_ANIO_MES.fullmatch(config.anio_mes_maximo):
        raise ErrorConfig(
            f"{ruta_yml}: el campo 'anio_mes_maximo' vale '{config.anio_mes_maximo}', "
            f"se esperaba el formato YYYY-MM (por ejemplo 2026-08)"
        )

    for clave in ("prefijo", "ruta_local_datos"):
        valor = getattr(config, clave)
        if valor.startswith("/"):
            raise ErrorConfig(
                f"{ruta_yml}: el campo '{clave}' debe ser una ruta relativa, "
                f"se leyó '{valor}'"
            )


# ---------------------------------------------------------------------------
# Inventario declarado de archivos
# ---------------------------------------------------------------------------

RUTA_ARCHIVOS_YML = "load/config/archivos.yml"

# Claves admitidas por entrada. Cualquier otra es un typo y detiene la carga.
CLAVES_ARCHIVO = {
    "ruta",
    "tienda",
    "anio_mes",
    "sin_header",
    "columnas",
    "columnas_descartar",
    "copia_de",
}

MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}


@dataclass(frozen=True)
class ArchivoDeclarado:
    """Una entrada de `archivos.yml`: qué es cada CSV y qué le pasa."""

    ruta: str
    tienda: str
    anio_mes: str
    sin_header: bool = False
    columnas: tuple[str, ...] = ()
    columnas_descartar: tuple[str, ...] = ()
    copia_de: str | None = None

    @property
    def nombre(self) -> str:
        return os.path.basename(self.ruta)


def anio_mes_de_ruta(ruta: str) -> str:
    """Deriva el mes de la carpeta de origen: `2026/03_marzo/x.csv` -> `2026-03`.

    El mes de la partición sale de la ruta, no del contenido: es un hecho del
    proceso de captura y así se mantiene reproducible sin leer el archivo.
    """
    partes = ruta.split("/")
    if len(partes) < 3:
        raise ErrorConfig(f"ruta '{ruta}': se esperaba <anio>/<mes>/<archivo>.csv")
    anio, carpeta = partes[0], partes[1]
    nombre_mes = carpeta.split("_")[-1]
    if nombre_mes not in MESES:
        raise ErrorConfig(f"ruta '{ruta}': '{carpeta}' no corresponde a ningún mes")
    return f"{anio}-{MESES[nombre_mes]}"


def cargar_archivos(ruta_yml: str = RUTA_ARCHIVOS_YML) -> list[ArchivoDeclarado]:
    """Lee el inventario declarado y lo valida antes de devolverlo."""
    ruta = os.path.join(raiz_repo(), ruta_yml)

    if not os.path.exists(ruta):
        raise ErrorConfig(f"No se encontró el inventario de archivos: {ruta_yml}")

    with open(ruta, encoding="utf-8") as f:
        crudo = yaml.safe_load(f)

    if not isinstance(crudo, dict) or "archivos" not in crudo:
        raise ErrorConfig(f"{ruta_yml}: se esperaba una clave 'archivos' en la raíz")

    entradas = crudo["archivos"]
    if not isinstance(entradas, list) or not entradas:
        raise ErrorConfig(f"{ruta_yml}: 'archivos' debe ser una lista no vacía")

    declarados: list[ArchivoDeclarado] = []
    vistas: set[str] = set()

    for i, entrada in enumerate(entradas, start=1):
        if not isinstance(entrada, dict):
            raise ErrorConfig(f"{ruta_yml}: la entrada #{i} no es un mapeo de claves")

        sobrantes = sorted(set(entrada) - CLAVES_ARCHIVO)
        if sobrantes:
            raise ErrorConfig(
                f"{ruta_yml}: entrada #{i}: clave desconocida '{sobrantes[0]}'"
                + _y_ademas(sobrantes)
            )

        for clave in ("ruta", "tienda", "anio_mes"):
            valor = entrada.get(clave)
            if not isinstance(valor, str) or not valor.strip():
                raise ErrorConfig(f"{ruta_yml}: entrada #{i}: falta el campo '{clave}'")

        ruta_csv = entrada["ruta"].strip()
        if ruta_csv in vistas:
            raise ErrorConfig(f"{ruta_yml}: la ruta '{ruta_csv}' está declarada dos veces")
        vistas.add(ruta_csv)

        esperado = anio_mes_de_ruta(ruta_csv)
        if entrada["anio_mes"].strip() != esperado:
            raise ErrorConfig(
                f"{ruta_yml}: '{ruta_csv}' declara anio_mes "
                f"'{entrada['anio_mes'].strip()}' pero su carpeta dice '{esperado}'"
            )

        sin_header = bool(entrada.get("sin_header", False))
        columnas = _lista_de_textos(entrada.get("columnas"), "columnas", i, ruta_yml)
        if sin_header and not columnas:
            raise ErrorConfig(
                f"{ruta_yml}: '{ruta_csv}' es sin_header pero no declara sus 'columnas'"
            )

        declarados.append(
            ArchivoDeclarado(
                ruta=ruta_csv,
                tienda=entrada["tienda"].strip(),
                anio_mes=esperado,
                sin_header=sin_header,
                columnas=columnas,
                columnas_descartar=_lista_de_textos(
                    entrada.get("columnas_descartar"), "columnas_descartar", i, ruta_yml
                ),
                copia_de=(entrada.get("copia_de") or "").strip() or None,
            )
        )

    for d in declarados:
        if d.copia_de and d.copia_de not in vistas:
            raise ErrorConfig(
                f"{ruta_yml}: '{d.ruta}' declara copia_de '{d.copia_de}', "
                f"que no está en el inventario"
            )

    _validar_destinos_unicos(declarados, ruta_yml)
    return declarados


def _lista_de_textos(valor, clave: str, i: int, ruta_yml: str) -> tuple[str, ...]:
    """Una lista de nombres de columna, o error.

    Un escalar (`columnas_descartar: NDF` en vez de `[NDF]`) se convertiría en
    `('N', 'D', 'F')` y el fallo aparecería mucho después, culpando al CSV.
    """
    if valor is None:
        return ()
    if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
        raise ErrorConfig(
            f"{ruta_yml}: entrada #{i}: '{clave}' debe ser una lista de nombres "
            f"entre corchetes, se leyó {valor!r}"
        )
    return tuple(valor)


def _validar_destinos_unicos(declarados: list[ArchivoDeclarado], ruta_yml: str) -> None:
    """Dos rutas distintas no pueden escribir el mismo objeto en GCS.

    La ruta local es única por construcción, pero el destino es
    `(tienda, anio_mes, nombre)`: `2025/diciembre/x.csv` y `2025/12_diciembre/x.csv`
    son entradas distintas que se pisarían una a la otra.
    """
    destinos: dict[tuple[str, str, str], str] = {}
    for d in declarados:
        destino = (d.tienda, d.anio_mes, d.nombre)
        if destino in destinos:
            raise ErrorConfig(
                f"{ruta_yml}: '{d.ruta}' y '{destinos[destino]}' escriben el mismo "
                f"destino tienda={d.tienda}/anio_mes={d.anio_mes}/{d.nombre}"
            )
        destinos[destino] = d.ruta
