{% docs __overview__ %}

# Precios — modelo de datos

Pipeline ELT de precios de medicamentos en ecommerce mexicanos. Este proyecto dbt
es la parte de transformación: parte de las external tables de `precios_bronce` y
construye las capas silver y gold sobre BigQuery.

## Capas

| Capa | Dataset | Materialización | Qué es |
| --- | --- | --- | --- |
| staging | `precios_silver` | vista | Tipado y limpieza 1:1 con la source. `stg_precios`, `stg_ndf`. |
| silver | `precios_silver` | tabla | Universo depurado. `precios` (filas válidas, sin duplicados exactos) y `precios_cuarentena` (lo descartado, con su `motivo_descarte`). Particionadas por `mes`. |
| gold | `precios_gold` | tabla | Star schema: `fact_precios` y sus dimensiones. |

El seed `tiendas` (catálogo propio de 19 tiendas) aterriza en `precios_bronce`: es
dato de entrada curado a mano, no un modelo de capa.

## Star schema (gold)

`fact_precios` tiene grano `(producto_key, fecha_key)` — un precio de lista y un
precio de oferta por producto y día. Se construye contra `silver.precios` en este
orden:

1. `dim_tienda` — 19 filas, viene del seed `tiendas`.
2. `dim_fecha` — una fila por día natural del histórico observado, con
   `dbt_utils.date_spine` entre el `min` y el `max` de `fecha_captura`.
3. `dim_producto` — grano `(tienda_key, sku)`, ~160 mil productos. Es el insumo
   del entity resolution: el texto del producto vive aquí, no en la fact.
4. `fact_precios` — dedup incluido: colapsa las ~17 mil filas de exceso de silver
   quedándose con el precio de lista más bajo observado cada día.

`dim_ndf` se construye por su cuenta desde el catálogo NDF (`stg_ndf`), sin tocar
`silver.precios`. El cruce entre `dim_producto` y `dim_ndf` (asignar `ndf_id` a
cada producto de tienda) es el entity resolution, todavía pendiente.

## Decisiones que el lector nuevo debe conocer

- **`precio_oferta` es NULL cuando no hay descuento real, nunca `0`.** Un centinela
  `0` en una columna numérica corrompe cualquier `MIN()` o `AVG()` aguas abajo.
- **`producto` significa dos cosas distintas.** En `dim_producto` es el nombre del
  listing en la tienda; en `dim_ndf` es la marca comercial del catálogo. Viven en
  dimensiones distintas justamente por eso.
- **`ndf_id` no lleva ceros a la izquierda.** Cualquier crosswalk externo que
  llegue con padding hay que normalizarlo antes de joinear.
- **`tienda_key` no se reasigna nunca.** Reciclar el número de una tienda dada de
  baja corrompe el histórico de la fact.

## Documentación

Esta página y las descripciones de cada modelo y columna se generan con
`dbt docs generate` y se navegan con `dbt docs serve` (levanta un portal web
local con el DAG, el linaje columna a columna y el catálogo de BigQuery).

{% enddocs %}
