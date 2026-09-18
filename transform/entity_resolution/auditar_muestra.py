"""Genera la muestra estratificada para auditar el matching aportador-NDF.

Consulta ``precios_gold.dim_producto`` en BigQuery -los productos de
tienda que ya tienen ``ndf_id`` asignado por la pasada de aportadores- y
saca 25 pares por tienda con semilla fija, para producir
``salida/catalogos/auditoria_aportadores.csv`` con la columna ``correcto``
vacía, lista para llenarse a mano con 1 o 0.

Se corre con:

    uv run --project transform transform/entity_resolution/auditar_muestra.py

Requiere ADC (``gcloud auth application-default login``) sin
``quota_project_id`` fijado -igual que dbt y ``load/``, ver
``transform/dbt/precios/profiles.yml``-.
"""

import csv
import os
import random
from collections import defaultdict

from google.cloud import bigquery

PROJECT_ID = "scenic-firefly-473823-f7"
LOCATION = "US"
CSV_SALIDA = "./salida/catalogos/auditoria_aportadores.csv"
PARES_POR_TIENDA = 25
SEMILLA = 57  # Fija: dos corridas deben producir la misma muestra (ALD-57).

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

    El ``order by`` de la consulta fija el orden de llegada de las filas:
    sin eso, dos corridas podrían traer el mismo conjunto en distinto
    orden y la semilla fija de ``random.Random`` ya no reproduciría la
    misma muestra.
    """
    cliente = bigquery.Client(project=PROJECT_ID, location=LOCATION)
    filas_por_tienda = defaultdict(list)
    for fila in cliente.query(CONSULTA).result():
        filas_por_tienda[fila.tienda_slug].append(
            {
                "url_tienda": fila.url_tienda,
                "descripcion_tienda": fila.descripcion_tienda,
                "presentacion_ndf": fila.presentacion_ndf,
            }
        )
    return filas_por_tienda


def muestrear(filas_por_tienda):
    """Saca PARES_POR_TIENDA filas al azar por tienda, con semilla fija.

    Una sola instancia de ``Random``, alimentada en orden alfabético de
    tienda, para que la muestra sea reproducible entre corridas. Una
    tienda con menos candidatos que ``PARES_POR_TIENDA`` -match casi nulo
    contra el aportador, como yza, ver ``dim_producto.sql``- se salta
    entera en vez de tomar una muestra parcial que rompería "25 por
    tienda".
    """
    rng = random.Random(SEMILLA)
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
            writer.writerow({**fila, "correcto": ""})


def main():
    filas_por_tienda = consultar_candidatos()
    muestra = muestrear(filas_por_tienda)
    escribir_csv(muestra, CSV_SALIDA)
    print(
        f"✅ {len(muestra)} filas ({len(filas_por_tienda)} tiendas) "
        f"-> {CSV_SALIDA}"
    )


if __name__ == "__main__":
    main()
