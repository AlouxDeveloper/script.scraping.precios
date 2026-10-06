"""Genera y reporta la muestra estratificada de auditoría del match
aportador-NDF.

Modo por defecto: consulta ``precios_gold.dim_producto`` en BigQuery -los
productos de tienda que ya tienen ``ndf_id`` asignado por la pasada de
aportadores- y saca 25 pares por tienda con semilla fija, para producir
``salida/catalogos/auditoria_aportadores.csv`` con la columna ``correcto``
vacía, lista para llenarse a mano con 1 o 0 (ver ALD-57). También escribe
``auditoria_aportadores_tiendas.csv``, sidecar interno con la tienda de
cada fila que ``--reportar`` necesita y que el auditor no debe tocar.

Modo ``--reportar``: una vez llena esa columna a mano (ALD-58), calcula
precisión global, precisión por tienda e intervalo de confianza binomial
de Wilson al 95%.

Se corre con:

    uv run --project transform transform/entity_resolution/auditar_muestra.py
    uv run --project transform transform/entity_resolution/auditar_muestra.py --reportar

Requiere ADC (``gcloud auth application-default login``) sin
``quota_project_id`` fijado -igual que dbt y ``load/``, ver
``transform/dbt/precios/profiles.yml``-.
"""

import csv
import os
import sys
from collections import defaultdict
from random import Random

from google.cloud import bigquery

PROJECT_ID = "scenic-firefly-473823-f7"
LOCATION = "US"
CSV_SALIDA = "./salida/catalogos/auditoria_aportadores.csv"
# Sidecar interno (no lo edita el auditor): tienda_slug por fila, en el
# mismo orden que CSV_SALIDA. url_tienda no sirve como llave para
# reconstruirla después -aurrera y walmart comparten url_producto_actual
# idéntica en varios productos (mismo catálogo, dominio walmart.com.mx)-,
# así que en vez de adivinar por texto se guarda la tienda real al
# generar la muestra.
RUTA_TIENDAS = "./salida/catalogos/auditoria_aportadores_tiendas.csv"
PARES_POR_TIENDA = 25
SEMILLA = 57  # Fija: dos corridas deben producir la misma muestra (ALD-57).
CORTE_PRECISION = 0.95  # Umbral del issue: por debajo, el set no sirve.
MODO_REPORTAR = "--reportar"

COLUMNAS_SALIDA = [
    "url_tienda",
    "descripcion_tienda",
    "presentacion_ndf",
    "correcto",
]

# El inner join contra dim_ndf es el filtro: dim_producto.ndf_id solo trae
# ids reales -sin candidatos ambiguos ni huecos del catálogo, ver el CTE
# match_aportador en dim_producto.sql-, así que unirlos ya selecciona "los
# artículos que ya tienen ndf".
CONSULTA = """
    select
        dim_tienda.tienda_slug,
        dim_producto.descripcion as descripcion_tienda,
        dim_producto.url_producto_actual as url_tienda,
        dim_ndf.presentacion as presentacion_ndf
    from precios_gold.dim_producto as dim_producto
    inner join precios_gold.dim_tienda as dim_tienda
        using (tienda_key)
    inner join precios_gold.dim_ndf as dim_ndf
        on dim_producto.ndf_id = dim_ndf.ndf_id
    order by dim_tienda.tienda_slug, descripcion_tienda, url_tienda
"""


def consultar_candidatos():
    """Trae de BigQuery los productos de tienda ya matcheados a ndf_id.

    Devuelve una lista plana (una fila por producto, con su tienda_slug)
    para que tanto ``generar_muestra`` como ``reportar`` puedan agruparla
    como necesiten sin repetir la consulta.

    El ``order by`` de la consulta fija el orden de llegada de las filas:
    sin eso, dos corridas podrían traer el mismo conjunto en distinto
    orden y la semilla fija de ``Random`` ya no reproduciría la misma
    muestra.
    """
    cliente = bigquery.Client(project=PROJECT_ID, location=LOCATION)
    return [
        {
            "tienda_slug": fila.tienda_slug,
            "url_tienda": fila.url_tienda,
            "descripcion_tienda": fila.descripcion_tienda,
            "presentacion_ndf": fila.presentacion_ndf,
        }
        for fila in cliente.query(CONSULTA).result()
    ]


def agrupar_por_tienda(filas):
    """Agrupa una lista plana de filas por su tienda_slug."""
    agrupado = defaultdict(list)
    for fila in filas:
        agrupado[fila["tienda_slug"]].append(fila)
    return agrupado


def muestrear(filas_por_tienda):
    """Saca PARES_POR_TIENDA filas al azar por tienda, con semilla fija.

    Una sola instancia de ``Random``, alimentada en orden alfabético de
    tienda, para que la muestra sea reproducible entre corridas. Una
    tienda con menos candidatos que ``PARES_POR_TIENDA`` -match casi nulo
    contra el aportador, como yza, ver ``dim_producto.sql``- se salta
    entera en vez de tomar una muestra parcial que rompería "25 por
    tienda".
    """
    rng = Random(SEMILLA)
    muestra = []
    for tienda in sorted(filas_por_tienda):
        filas = filas_por_tienda[tienda]
        if len(filas) < PARES_POR_TIENDA:
            print(f"⚠️  {tienda}: solo {len(filas)} candidatos, se salta")
            continue
        muestra.extend(rng.sample(filas, PARES_POR_TIENDA))
    return muestra


def escribir_csv(muestra, ruta):
    """Escribe la hoja de auditoría con la columna correcto vacía."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS_SALIDA)
        writer.writeheader()
        for fila in muestra:
            writer.writerow(
                {
                    "url_tienda": fila["url_tienda"],
                    "descripcion_tienda": fila["descripcion_tienda"],
                    "presentacion_ndf": fila["presentacion_ndf"],
                    "correcto": "",
                }
            )


def escribir_tiendas(muestra, ruta):
    """Escribe el sidecar tienda_slug por fila, alineado con escribir_csv."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tienda_slug"])
        writer.writeheader()
        for fila in muestra:
            writer.writerow({"tienda_slug": fila["tienda_slug"]})


def generar_muestra():
    """Modo por defecto: genera la hoja de auditoría desde BigQuery."""
    filas_por_tienda = agrupar_por_tienda(consultar_candidatos())
    muestra = muestrear(filas_por_tienda)
    escribir_csv(muestra, CSV_SALIDA)
    escribir_tiendas(muestra, RUTA_TIENDAS)
    print(
        f"✅ {len(muestra)} filas ({len(filas_por_tienda)} tiendas) "
        f"-> {CSV_SALIDA}"
    )


def intervalo_wilson(aciertos, n, z=1.96):
    """Intervalo de confianza binomial de Wilson al 95% (z=1.96).

    Wilson en vez del intervalo normal (Wald): la precisión esperada acá
    está cerca de 1 -el corte del issue es 0.95-, y ahí Wald puede dar un
    límite superior mayor a 1 y subestima el error cerca de los extremos;
    Wilson no.
    """
    p = aciertos / n
    denominador = 1 + z**2 / n
    centro = (p + z**2 / (2 * n)) / denominador
    margen = (
        z
        * ((p * (1 - p) / n) + (z**2 / (4 * n**2))) ** 0.5
        / denominador
    )
    return centro - margen, centro + margen


def reportar():
    """Modo --reportar: precisión global, por tienda e IC de la auditoría.

    La tienda de cada fila no vive en el CSV auditado (ALD-57 la dejó
    fuera a propósito, solo 4 columnas): se recupera del sidecar
    RUTA_TIENDAS por posición, no cruzando por url_tienda -ver el
    comentario de RUTA_TIENDAS sobre la colisión aurrera/walmart-.
    """
    if not os.path.exists(CSV_SALIDA) or not os.path.exists(RUTA_TIENDAS):
        print(
            f"❌ Falta {CSV_SALIDA} o {RUTA_TIENDAS}, "
            "corre primero sin --reportar"
        )
        return

    with open(CSV_SALIDA, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    with open(RUTA_TIENDAS, encoding="utf-8", newline="") as f:
        tiendas = [fila["tienda_slug"] for fila in csv.DictReader(f)]

    if len(filas) != len(tiendas):
        print(
            f"❌ {CSV_SALIDA} ({len(filas)} filas) y {RUTA_TIENDAS} "
            f"({len(tiendas)} filas) no cuadran, ¿se regeneró uno sin el "
            "otro?"
        )
        return

    faltantes = sum(1 for fila in filas if fila["correcto"] not in ("0", "1"))
    if faltantes:
        print(f"❌ {faltantes} filas sin correcto lleno (0 o 1), falta auditar")
        return

    por_tienda = defaultdict(lambda: [0, 0])  # tienda -> [aciertos, n]
    aciertos_global = 0
    for fila, tienda in zip(filas, tiendas):
        acierto = int(fila["correcto"])
        por_tienda[tienda][0] += acierto
        por_tienda[tienda][1] += 1
        aciertos_global += acierto

    n = len(filas)
    precision_global = aciertos_global / n
    lo, hi = intervalo_wilson(aciertos_global, n)
    print(
        f"Precisión global: {precision_global:.3f} "
        f"({aciertos_global}/{n}), IC95% [{lo:.3f}, {hi:.3f}]"
    )
    print(f"{'tienda':<12}{'n':>5}{'aciertos':>10}{'precisión':>11}  IC95%")
    for tienda in sorted(por_tienda):
        aciertos, total = por_tienda[tienda]
        p = aciertos / total
        lo_t, hi_t = intervalo_wilson(aciertos, total)
        print(
            f"{tienda:<12}{total:>5}{aciertos:>10}{p:>11.3f}  "
            f"[{lo_t:.3f}, {hi_t:.3f}]"
        )

    if precision_global >= CORTE_PRECISION:
        print(
            f"✅ Precisión {precision_global:.3f} >= {CORTE_PRECISION}: "
            "el set sirve como verdad, el plan sigue."
        )
    else:
        print(
            f"⚠️  Precisión {precision_global:.3f} < {CORTE_PRECISION}: "
            "hay que etiquetar un set propio, replantear el milestone."
        )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == MODO_REPORTAR:
        reportar()
    else:
        generar_muestra()


if __name__ == "__main__":
    main()
