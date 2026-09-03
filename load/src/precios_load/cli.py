"""CLI de la capa de ingesta.

Se ejecuta siempre desde la raíz del repo:

    uv run --project load python -m precios_load.cli plan
"""

import typer

from precios_load import __version__, bq, manifest
from precios_load.clientes import cliente_bq, cliente_gcs
from precios_load.config import (
    FORMATO_ANIO_MES,
    ErrorConfig,
    cargar_archivos,
    cargar_config,
)
from precios_load.descubrimiento import ErrorDescubrimiento, descubrir
from precios_load.esquemas import ErrorEsquema
from precios_load.ingesta import ejecutar
from precios_load.plan import construir_plan, render
from precios_load.rutas import raiz_repo

app = typer.Typer(
    help="Ingesta del histórico de precios a Cloud Storage y BigQuery.",
    no_args_is_help=True,
    add_completion=False,
)

# Los comandos se implementan en los issues siguientes; el esqueleto ya fija
# la firma para que el orden de trabajo no tenga que renombrar nada.
PENDIENTE = "⏳ Comando aún no implementado ({issue})."


@app.callback()
def principal(ctx: typer.Context) -> None:
    """Valida la raíz del repo y la configuración antes de cualquier comando."""
    raiz_repo()
    try:
        ctx.obj = cargar_config()
    except ErrorConfig as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def version() -> None:
    """Imprime la versión del paquete."""
    typer.echo(__version__)


@app.command()
def config(ctx: typer.Context) -> None:
    """Muestra la configuración ya validada y las rutas que se derivan de ella."""
    cfg = ctx.obj
    typer.echo(f"project_id        {cfg.project_id}")
    typer.echo(f"location          {cfg.location}")
    typer.echo(f"dataset bronce    {cfg.tabla_bronce('<tabla>')}")
    typer.echo(f"dataset ops       {cfg.tabla_ops('<tabla>')}")
    typer.echo(f"conexión BigLake  {cfg.conexion()}")
    typer.echo(f"datos locales     {cfg.ruta_datos()}")
    typer.echo(f"ingiere hasta     {cfg.anio_mes_maximo} (inclusive)")
    typer.echo(f"raw               {cfg.uri_raw('<tienda>', '<anio_mes>', '<archivo>.csv')}")
    typer.echo(f"bronce            {cfg.uri_bronce('<tienda>', '<anio_mes>', '<archivo>.parquet')}")


@app.command()
def plan(
    ctx: typer.Context,
    tienda: str = typer.Option(None, help="Filtra por slug de tienda."),
    mes: str = typer.Option(None, help="Filtra por mes, formato YYYY-MM."),
    hasta: str = typer.Option(
        None, help="Último mes a considerar. Por defecto, anio_mes_maximo de gcp.yml."
    ),
    resumen: bool = typer.Option(False, help="Solo los totales, sin el detalle por archivo."),
) -> None:
    """Dry-run: qué se subiría y qué se salta. No toca Google Cloud."""
    cfg = ctx.obj

    for nombre, valor in (("--mes", mes), ("--hasta", hasta)):
        _validar_mes(nombre, valor)

    try:
        declarados = cargar_archivos()
        descubrimiento = descubrir(declarados=declarados, hasta=hasta)
    except (ErrorConfig, ErrorDescubrimiento, ErrorEsquema) as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(code=1) from e

    if tienda:
        _validar_tienda(tienda, declarados)

    if mes and mes > descubrimiento.hasta:
        typer.echo(
            f"⚠️  --mes {mes} queda fuera del corte {descubrimiento.hasta}. "
            f"Añade --hasta {mes} para incluirlo.",
            err=True,
        )
    elif mes and mes not in {d.anio_mes for d in declarados}:
        typer.echo(f"⚠️  No hay ningún archivo declarado del mes {mes}.", err=True)

    if descubrimiento.sin_declarar:
        typer.echo(
            f"⚠️  {len(descubrimiento.sin_declarar)} archivo(s) sin declarar en meses "
            f"posteriores a {descubrimiento.hasta}, no se ingieren:\n  "
            + "\n  ".join(descubrimiento.sin_declarar),
            err=True,
        )

    for linea in render(
        construir_plan(descubrimiento, cfg, declarados, tienda=tienda, mes=mes),
        cfg,
        resumen=resumen,
    ):
        typer.echo(linea)


@app.command()
def ingesta(
    ctx: typer.Context,
    tienda: str = typer.Option(None, help="Filtra por slug de tienda."),
    mes: str = typer.Option(None, help="Filtra por mes, formato YYYY-MM."),
) -> None:
    """Sube a raw los archivos que cambiaron y registra el resultado en el manifest."""
    cfg = ctx.obj
    _validar_mes("--mes", mes)

    # Un --mes posterior al corte de gcp.yml lo amplía: pedir un mes explícito es
    # una decisión deliberada (así se ingiere el mes en curso en ALD-19).
    hasta = mes if (mes and mes > cfg.anio_mes_maximo) else None

    try:
        declarados = cargar_archivos()
        descubrimiento = descubrir(declarados=declarados, hasta=hasta)
    except (ErrorConfig, ErrorDescubrimiento, ErrorEsquema) as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(code=1) from e

    if tienda:
        _validar_tienda(tienda, declarados)

    plan = construir_plan(descubrimiento, cfg, declarados, tienda=tienda, mes=mes)
    if not plan.entradas:
        typer.echo("No hay archivos que ingerir con esos filtros.")
        return

    resultado = ejecutar(
        cliente_bq(cfg), cliente_gcs(cfg), cfg, list(plan.entradas)
    )

    for ruta in resultado.procesados:
        typer.echo(f"→ {ruta}")
    for ruta in resultado.saltados:
        typer.echo(f"· {ruta}  (sin cambios)")
    for ruta, error in resultado.fallidos:
        typer.echo(f"❌ {ruta}: {error}", err=True)

    typer.echo(
        f"\nprocesados {len(resultado.procesados)}  "
        f"saltados {len(resultado.saltados)}  "
        f"fallidos {len(resultado.fallidos)}"
    )
    if resultado.fallidos:
        raise typer.Exit(code=1)


@app.command(name="bq-setup")
def bq_setup(ctx: typer.Context) -> None:
    """Crea o reemplaza la external table BigLake con hive partitioning sobre bronce."""
    cfg = ctx.obj
    cliente = cliente_bq(cfg)
    tabla = bq.crear_external_bronce(cliente, cfg)
    total = next(iter(cliente.query(f"SELECT COUNT(*) AS n FROM `{tabla}`").result()))["n"]
    typer.echo(f"external table  {tabla}")
    typer.echo(f"filas           {total:,}")


@app.command()
def estado(ctx: typer.Context) -> None:
    """Resumen del manifest de ingesta. Crea la tabla de control si no existe."""
    cfg = ctx.obj
    cliente = cliente_bq(cfg)
    for linea in manifest.resumen(cliente, cfg):
        typer.echo(linea)


@app.command()
def verificar(ctx: typer.Context) -> None:
    """Reconciliación de conteos entre local, GCS y BigQuery."""
    typer.echo(PENDIENTE.format(issue="ALD-25"))


def _validar_mes(nombre: str, valor: str | None) -> None:
    """Un mes mal escrito rompe la comparación de cadenas en silencio.

    `--hasta 2026-9` deja pasar septiembre, porque `"2026-09" <= "2026-9"`, que
    es justo lo que el corte tiene que impedir.
    """
    if valor is not None and not FORMATO_ANIO_MES.fullmatch(valor):
        typer.echo(
            f"❌ {nombre} {valor}: se esperaba el formato YYYY-MM (por ejemplo 2026-08).",
            err=True,
        )
        raise typer.Exit(code=1)


def _validar_tienda(tienda: str, declarados) -> None:
    """Un slug con typo daría un plan vacío indistinguible de 'ya no hay nada'."""
    slugs = sorted({d.tienda for d in declarados})
    if tienda not in slugs:
        typer.echo(
            f"❌ --tienda {tienda}: no está en archivos.yml.\n"
            f"   Slugs válidos: {', '.join(slugs)}",
            err=True,
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
