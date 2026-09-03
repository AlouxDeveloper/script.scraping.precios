"""El dry-run: qué se subiría, a dónde y por qué.

No abre conexión a Google Cloud ni resuelve credenciales. Todo lo que imprime
sale de `salida/data`, de `archivos.yml` y de `gcp.yml`, así que se puede
correr en cualquier máquina con el histórico local y sin red.
"""

import os
from dataclasses import dataclass

from precios_load.config import ArchivoDeclarado, ConfigGCP, anio_mes_de_ruta
from precios_load.descubrimiento import ArchivoFuente, Descubrimiento

# Acciones posibles para un archivo.
SUBE = "sube"
SALTA = "salta"

# Motivos de salto. El manifest de idempotencia añadirá los suyos en ALD-17.
MOTIVO_VACIO = "sin filas"


@dataclass(frozen=True)
class EntradaPlan:
    """Lo que pasaría con un archivo concreto."""

    fuente: ArchivoFuente
    uri_raw: str
    uri_bronce: str
    accion: str
    motivo: str
    flags: tuple[str, ...]

    @property
    def sube(self) -> bool:
        return self.accion == SUBE


@dataclass(frozen=True)
class Plan:
    """El dry-run completo, ya filtrado."""

    entradas: tuple[EntradaPlan, ...]
    faltantes: tuple[str, ...]
    fuera_de_rango: tuple[str, ...]
    hasta: str
    tienda: str | None = None
    mes: str | None = None

    @property
    def a_subir(self) -> tuple[EntradaPlan, ...]:
        return tuple(e for e in self.entradas if e.sube)

    def totales(self) -> tuple[int, int, int]:
        """Archivos, filas y bytes que se subirían."""
        subibles = self.a_subir
        return (
            len(subibles),
            sum(e.fuente.filas for e in subibles),
            sum(e.fuente.bytes for e in subibles),
        )

    def por(self, atributo: str) -> dict[str, tuple[int, int, int]]:
        """Desglose por `tienda` o por `anio_mes`: archivos, filas y bytes.

        Cuenta todos los archivos del plan, también los que se saltan: es el
        inventario de lo que hay, y el reparto entre subir y saltar ya lo dice
        el resumen.
        """
        desglose: dict[str, tuple[int, int, int]] = {}
        for e in self.entradas:
            clave = getattr(e.fuente, atributo)
            archivos, filas, bytes_ = desglose.get(clave, (0, 0, 0))
            desglose[clave] = (archivos + 1, filas + e.fuente.filas, bytes_ + e.fuente.bytes)
        return dict(sorted(desglose.items()))


def construir_plan(
    descubrimiento: Descubrimiento,
    config: ConfigGCP,
    declarados: list[ArchivoDeclarado],
    tienda: str | None = None,
    mes: str | None = None,
) -> Plan:
    """Cruza lo descubierto con la configuración y aplica los filtros.

    `declarados` es el inventario completo. Hace falta para saber de qué tienda
    son los archivos que no se midieron (faltantes y fuera de rango), que
    llegan como ruta suelta: sin él, un `--tienda` los escondería en silencio.
    """
    tienda_de = {d.ruta: d.tienda for d in declarados}

    def pasa_ruta(ruta: str) -> bool:
        return _pasa_filtros(tienda_de.get(ruta), anio_mes_de_ruta(ruta), tienda, mes)

    entradas = [
        _entrada(fuente, config)
        for fuente in descubrimiento.archivos
        if _pasa_filtros(fuente.tienda, fuente.anio_mes, tienda, mes)
    ]

    return Plan(
        entradas=tuple(entradas),
        faltantes=tuple(r for r in descubrimiento.faltantes if pasa_ruta(r)),
        fuera_de_rango=tuple(r for r in descubrimiento.fuera_de_rango if pasa_ruta(r)),
        hasta=descubrimiento.hasta or config.anio_mes_maximo,
        tienda=tienda,
        mes=mes,
    )


def _entrada(fuente: ArchivoFuente, config: ConfigGCP) -> EntradaPlan:
    nombre_parquet = os.path.splitext(fuente.nombre)[0] + ".parquet"
    vacio = fuente.vacio

    return EntradaPlan(
        fuente=fuente,
        uri_raw=config.uri_raw(fuente.tienda, fuente.anio_mes, fuente.nombre),
        uri_bronce=config.uri_bronce(fuente.tienda, fuente.anio_mes, nombre_parquet),
        accion=SALTA if vacio else SUBE,
        motivo=MOTIVO_VACIO if vacio else "",
        flags=_flags(fuente),
    )


def _flags(fuente: ArchivoFuente) -> tuple[str, ...]:
    """Lo que `archivos.yml` y el escaneo ya saben del archivo."""
    declarado = fuente.declarado
    flags = []
    if declarado.sin_header:
        flags.append("SIN_HEADER")
    if declarado.columnas_descartar:
        flags.append("DESCARTA:" + ",".join(declarado.columnas_descartar))
    if declarado.copia_de:
        flags.append("SOSPECHA_COPIA")
    if fuente.desfase:
        # El mes mayoritario solo se nombra cuando no es el de la carpeta: si
        # coincide, el desfase es de unas pocas filas sueltas.
        mayoritario = fuente.anio_mes_dato
        sufijo = f"→{mayoritario}" if mayoritario != declarado.anio_mes else ""
        flags.append(f"DESFASE_MES:{fuente.filas_desfasadas}{sufijo}")
    if fuente.vacio:
        flags.append("VACIO")
    return tuple(flags)


def _pasa_filtros(
    tienda_archivo: str | None, mes_archivo: str, tienda: str | None, mes: str | None
) -> bool:
    return (tienda is None or tienda_archivo == tienda) and (mes is None or mes_archivo == mes)


# ---------------------------------------------------------------------------
# Presentación
# ---------------------------------------------------------------------------


def formato_bytes(n: int) -> str:
    """`2570907` -> `2.5 MB`."""
    for unidad, umbral in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if n >= umbral:
            return f"{n / umbral:.1f} {unidad}"
    return f"{n} B"


def render(plan: Plan, config: ConfigGCP, resumen: bool = False) -> list[str]:
    """El dry-run como lista de líneas, para imprimir o para probar."""
    lineas = [
        f"Plan de ingesta — corte {plan.hasta} (inclusive)",
        f"  datos    {config.ruta_datos()}",
        f"  raw      {config.prefijo_raw()}",
        f"  bronce   {config.prefijo_bronce()}",
    ]
    if plan.tienda or plan.mes:
        filtros = [f"tienda={plan.tienda}" if plan.tienda else "", f"mes={plan.mes}" if plan.mes else ""]
        lineas.append("  filtros  " + " ".join(f for f in filtros if f))

    if not resumen:
        lineas.append("")
        lineas.extend(_lineas_por_archivo(plan))

    lineas.append("")
    lineas.extend(_lineas_resumen(plan))
    lineas.extend(_lineas_pendientes(plan))
    return lineas


def _lineas_por_archivo(plan: Plan) -> list[str]:
    if not plan.entradas:
        return ["Ningún archivo cumple los filtros."]

    lineas = [f"ARCHIVOS ({len(plan.entradas)})"]
    for e in plan.entradas:
        f = e.fuente
        marca = "→" if e.sube else "·"
        motivo = f"  ({e.motivo})" if e.motivo else ""
        flags = "  [" + " ".join(e.flags) + "]" if e.flags else ""
        lineas.append(
            f"{marca} {f.anio_mes}  {f.tienda:<11} {f.nombre:<42} {f.variante}"
            f"  {f.filas:>7,} filas  {formato_bytes(f.bytes):>8}  {e.accion}{motivo}{flags}"
        )
        lineas.append(f"    raw     {e.uri_raw}")
        lineas.append(f"    bronce  {e.uri_bronce}")
    return lineas


def _lineas_resumen(plan: Plan) -> list[str]:
    archivos, filas, bytes_ = plan.totales()
    saltados = len(plan.entradas) - archivos

    lineas = [
        "RESUMEN",
        f"  se subirían  {_plural(archivos)}  {filas:,} filas  {formato_bytes(bytes_)}",
        f"  se saltarían {_plural(saltados)}",
        "",
        "POR TIENDA",
    ]
    lineas.extend(_tabla(plan.por("tienda")))
    lineas.append("")
    lineas.append("POR MES")
    lineas.extend(_tabla(plan.por("anio_mes")))
    return lineas


def _plural(n: int) -> str:
    return f"{n} archivo" + ("" if n == 1 else "s")


def _tabla(desglose: dict[str, tuple[int, int, int]]) -> list[str]:
    return [
        f"  {clave:<12} {archivos:>3} archivos  {filas:>9,} filas  {formato_bytes(bytes_):>8}"
        for clave, (archivos, filas, bytes_) in desglose.items()
    ]


def _lineas_pendientes(plan: Plan) -> list[str]:
    lineas = []
    if plan.fuera_de_rango:
        lineas.append("")
        lineas.append(f"FUERA DEL CORTE ({len(plan.fuera_de_rango)}) — posteriores a {plan.hasta}")
        lineas.extend(f"  {r}" for r in plan.fuera_de_rango)
        ultimo = max(anio_mes_de_ruta(r) for r in plan.fuera_de_rango)
        lineas.append(f"  Para incluirlos: --hasta {ultimo}")
    if plan.faltantes:
        lineas.append("")
        lineas.append(f"DECLARADOS QUE NO ESTÁN EN DISCO ({len(plan.faltantes)})")
        lineas.extend(f"  {r}" for r in plan.faltantes)
    return lineas
