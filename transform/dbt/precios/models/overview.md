{% docs __overview__ %}

# Precios — modelo de datos

Pipeline ELT de precios de medicamentos en ecommerce mexicanos. Este proyecto dbt
es la parte de transformación: parte de las external tables de `precios_bronce` y
construye las capas silver y gold sobre BigQuery.

## Capas

| Capa | Dataset | Materialización | Qué es |
| --- | --- | --- | --- |
| staging | `precios_silver` | vista | Tipado y limpieza 1:1 con la source. `stg_precios`, `stg_ndf`, `stg_puente_aportador`. |
| silver | `precios_silver` | tabla | Universo depurado. `precios` (filas válidas, sin duplicados exactos) y `precios_cuarentena` (lo descartado, con su `motivo_descarte`). Particionadas por `mes`. |
| gold | `precios_gold` | tabla | Star schema: `fact_precios` y sus dimensiones. |
| ml | `precios_ml` | — | Entity resolution vectorial: el banco de embeddings y los modelos de búsqueda. Dataset y conexión BigLake a Vertex AI ya provisionados; sin modelos todavía. Va en su propio dataset porque gold se reconstruye entera en cada build y los embeddings son llamadas a la API ya pagadas: la frontera tiene que ser física, no una convención. |

El seed `tiendas` (catálogo propio de 19 filas, una por tienda scrapeada)
aterriza en `precios_bronce`: es dato de entrada curado a mano, no un modelo
de capa.

## Star schema (gold)

`fact_precios` tiene grano `(producto_key, fecha_key)` — un precio de lista y un
precio de oferta por producto y día. Se construye contra `silver.precios` en este
orden:

1. `dim_tienda` — 19 filas, viene del seed `tiendas`.
2. `dim_fecha` — una fila por día natural del histórico observado, con
   `dbt_utils.date_spine` entre el `min` y el `max` de `fecha_captura`.
3. `dim_producto` — grano `(tienda_key, sku)`, ~240 mil productos. Es el insumo
   del entity resolution: el texto del producto vive aquí, no en la fact.
   Lleva `ndf_id`/`match_method` parciales — ver abajo.
4. `fact_precios` — dedup incluido: colapsa las ~17 mil filas de exceso de silver
   quedándose con el precio de lista más bajo observado cada día.

`dim_ndf` se construye por su cuenta desde el catálogo NDF (`stg_ndf`), sin tocar
`silver.precios`. `dim_puente_aportador` es el crosswalk tienda-sku-ndf de
Knobloch (grano `tienda_key`, `sku`, `ndf_id`), también aparte de
`silver.precios`. Su `sku` **no coincide** con la mayoría de las tiendas (match
0-35% según tienda, ver `stg_puente_aportador`): parece un identificador propio
del aportador (EAN/UPC), no el mismo dato con otro formato.

**Primera pasada del entity resolution, ya en `dim_producto`.** Donde
`(tienda_key, sku)` mapea a exactamente un `ndf_id` real (existe en `dim_ndf`,
sin ambigüedad), `dim_producto.ndf_id` queda asignado con
`match_method = 'aportadores'` — 61,085 de 240,400 filas (~25%; el alta del
`aportador_clave` real de `fesa`/`yza` no movió el total, mismo patrón 0%
de sku sin match que otras tiendas). El resto queda `ndf_id`/`match_method`
NULL a la espera de una segunda pasada por texto (embeddings contra
`dim_ndf`), todavía no implementada. `match_method` está pensado para
acumular más de un valor a medida que se agreguen más métodos, no para
reemplazarse.

**Cómo va a llegar el resto.** El plan ataca primero el recorte del
laboratorio Sanfer (`upper(laboratorio) = 'SANFER'`, ~1,400 `ndf_id`) y
después el catálogo completo, con la misma infraestructura. La dirección
de la búsqueda cambia entre las dos fases y no es un detalle: con una base
de 1,400 vectores —el 0.8% del catálogo— el vecino más cercano de
cualquier producto es un artefacto del recorte, así que se busca
NDF→producto; con el catálogo entero el vecino más cercano vuelve a
significar algo y se invierte a producto→NDF top-1. Los umbrales de
aceptación son **por tienda**, no uno global: `presentacion` está
homologada, pero `descripcion` varía mucho de estilo entre tiendas
—walmart escribe largo, sanpablo corto— y la misma distancia coseno no
significa lo mismo en las dos.

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
