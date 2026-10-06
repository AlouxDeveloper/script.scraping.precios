"""Genera y reporta la auditoría de los matches vectoriales de huérfanos.

Huérfano es un producto sin ``ndf_id`` por crosswalk (``dim_producto``) al
que ``int_match_ndf`` le asignó uno con decisión ``vectorial`` (ALD-96).
Todas las precisiones del vectorial se midieron en tiendas con crosswalk;
esta muestra mide las tiendas a las que el vectorial les da cobertura.

Modo por defecto: saca ``PARES_POR_ESTRATO`` filas por estrato
(tienda, división del NDF), con semilla fija, y escribe
``salida/catalogos/auditoria_huerfanos.csv`` con la columna ``correcto``
vacía. Criterio de ALD-58: ``1`` solo si es el mismo producto **y** la
misma presentación.

Modo ``--reportar``: precisión global, por división, por tienda y por
estrato, con intervalo de Wilson al 95%.

Se corre, desde la raíz del repo, con:

    uv run --project transform transform/entity_resolution/auditar_huerfanos.py
    uv run --project transform transform/entity_resolution/auditar_huerfanos.py --reportar
"""

import csv
import os
import sys
from collections import defaultdict
from random import Random

from google.cloud import bigquery

from auditar_muestra import LOCATION, PROJECT_ID, intervalo_wilson

CSV_SALIDA = "./salida/catalogos/auditoria_huerfanos.csv"
PARES_POR_ESTRATO = 8
# Un estrato con menos filas se omite: 8 de 34 estratos suman ~25
# productos de 6,194 y no alcanzan para decir nada de su tienda.
MINIMO_ESTRATO = 10
SEMILLA = 96  # Fija: dos corridas producen la misma muestra.
MODO_REPORTAR = "--reportar"
OBJETIVO = {"FARMA": 0.95, "NO FARMA": 0.85}
# Regla del issue: una tienda más de 5 pp abajo del objetivo se ajusta.
TOLERANCIA = 0.05

# La tienda y la división van en el CSV, a diferencia de ALD-57: ahí
# aurrera y walmart comparten url y hubo que usar un archivo aparte; aquí
# van en columnas propias y no hace falta reconstruirlas.
COLUMNAS_SALIDA = [
    "producto_key",
    "tienda_slug",
    "division",
    "descripcion_tienda",
    "presentacion_ndf",
    "correcto",
]

CONSULTA = """
    select
        m.producto_key,
        t.tienda_slug,
        n.division,
        p.descripcion as descripcion_tienda,
        n.presentacion as presentacion_ndf
    from precios_ml.int_match_ndf as m
    inner join precios_gold.dim_producto as p using (producto_key)
    inner join precios_gold.dim_tienda as t using (tienda_key)
    inner join precios_gold.dim_ndf as n on n.ndf_id = m.ndf_id
    where m.decision = 'vectorial' and p.ndf_id is null
    order by t.tienda_slug, n.division, m.producto_key
"""


def consultar_huerfanos():
    """Trae los huérfanos con decisión vectorial, agrupados por estrato.

    El ``order by`` fija el orden de llegada para que la semilla
    reproduzca la misma muestra entre corridas.
    """
    cliente = bigquery.Client(project=PROJECT_ID, location=LOCATION)
    por_estrato = defaultdict(list)
    for fila in cliente.query(CONSULTA).result():
        por_estrato[(fila.tienda_slug, fila.division)].append(dict(fila))
    return por_estrato


def muestrear(por_estrato):
    """Saca PARES_POR_ESTRATO filas por estrato, en orden fijo de estrato."""
    rng = Random(SEMILLA)
    muestra = []
    for estrato in sorted(por_estrato):
        filas = por_estrato[estrato]
        if len(filas) < MINIMO_ESTRATO:
            print(f"⚠️  {estrato}: solo {len(filas)} filas, se omite")
            continue
        muestra.extend(rng.sample(filas, PARES_POR_ESTRATO))
    return muestra


def generar_muestra():
    """Modo por defecto: escribe la hoja de auditoría con correcto vacío."""
    muestra = muestrear(consultar_huerfanos())
    os.makedirs(os.path.dirname(CSV_SALIDA), exist_ok=True)
    with open(CSV_SALIDA, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS_SALIDA)
        writer.writeheader()
        for fila in muestra:
            writer.writerow({**fila, "correcto": ""})
    print(f"✅ {len(muestra)} filas -> {CSV_SALIDA}")


def imprimir_grupo(titulo, grupos):
    """Imprime aciertos, precisión e IC de Wilson de cada grupo."""
    print(f"\n{titulo}")
    for clave in sorted(grupos):
        aciertos, n = grupos[clave]
        lo, hi = intervalo_wilson(aciertos, n)
        etiqueta = " / ".join(clave) if isinstance(clave, tuple) else clave
        print(
            f"  {etiqueta:<26}{n:>4}{aciertos:>5}{aciertos / n:>8.3f}"
            f"  [{lo:.3f}, {hi:.3f}]"
        )


def reportar():
    """Modo --reportar: precisión por división, tienda y estrato.

    Con 8 filas por estrato el intervalo mide ±20 pp, así que un estrato
    solo se marca para ajuste cuando el límite superior de Wilson queda
    debajo de ``objetivo - TOLERANCIA``: ahí sí es seguro que está más de
    5 pp abajo, no solo que la muestra salió mala.
    """
    if not os.path.exists(CSV_SALIDA):
        print(f"❌ Falta {CSV_SALIDA}, corre primero sin --reportar")
        return
    with open(CSV_SALIDA, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    faltantes = sum(1 for fila in filas if fila["correcto"] not in ("0", "1"))
    if faltantes:
        print(f"❌ {faltantes} filas sin correcto lleno (0 o 1), falta auditar")
        return

    por_division = defaultdict(lambda: [0, 0])
    por_tienda = defaultdict(lambda: [0, 0])
    por_estrato = defaultdict(lambda: [0, 0])
    for fila in filas:
        acierto = int(fila["correcto"])
        claves = (
            (por_division, fila["division"]),
            (por_tienda, fila["tienda_slug"]),
            (por_estrato, (fila["tienda_slug"], fila["division"])),
        )
        for grupo, clave in claves:
            grupo[clave][0] += acierto
            grupo[clave][1] += 1

    imprimir_grupo("Por división", por_division)
    imprimir_grupo("Por tienda", por_tienda)
    imprimir_grupo("Por estrato", por_estrato)

    print()
    for (tienda, division), (aciertos, n) in sorted(por_estrato.items()):
        _, hi = intervalo_wilson(aciertos, n)
        if hi < OBJETIVO[division] - TOLERANCIA:
            print(
                f"⚠️  {tienda} / {division}: IC superior {hi:.3f} < "
                f"{OBJETIVO[division] - TOLERANCIA:.2f}, ajustar"
            )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == MODO_REPORTAR:
        reportar()
    else:
        generar_muestra()


if __name__ == "__main__":
    main()
