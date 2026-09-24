{% docs __overview__ %}

# Precios — modelo de datos

Pipeline ELT de precios de medicamentos en ecommerce mexicanos. Este proyecto dbt
es la parte de transformación: parte de las external tables de `precios_bronce` y
construye las capas silver y gold sobre BigQuery.

## Capas

| Capa | Dataset | Materialización | Qué es |
| --- | --- | --- | --- |
| staging | `precios_silver` | vista | Tipado y limpieza 1:1 con la source. `stg_precios`, `stg_ndf`, `stg_puente_aportador`. |
| silver | `precios_silver` | tabla | Universo depurado. `precios` (filas válidas, sin duplicados exactos) y `precios_cuarentena` (lo descartado, con su `motivo_descarte`), particionadas por `mes`. Además `int_producto` (producto con los cruces por código, entrada del entity resolution) y `ndf_cuarentena` (la banda gris del vectorial, entrada del método 3). |
| gold | `precios_gold` | tabla | Star schema: `fact_precios` y sus dimensiones. |
| ml | `precios_ml` | tabla / vista / incremental | Entity resolution vectorial: texto a vectorizar, banco de embeddings, búsqueda, decisión y vistas de calibración (`rev_`). Va en su propio dataset porque gold se reconstruye entera en cada build y los embeddings son llamadas a la API ya pagadas: la frontera tiene que ser física, no una convención. |

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
3. `dim_producto` — grano `(tienda_key, sku)`, ~240 mil productos. El texto
   del producto vive aquí, no en la fact. Lleva el `ndf_id` que haya
   encontrado el entity resolution y el `match_method` que lo encontró — ver
   abajo. Se arma sobre `int_producto` (silver), que es la misma tabla sin la
   pasada vectorial.
4. `fact_precios` — dedup incluido: colapsa las ~17 mil filas de exceso de silver
   quedándose con el precio de lista más bajo observado cada día.

`dim_ndf` se construye por su cuenta desde el catálogo NDF (`stg_ndf`), sin tocar
`silver.precios`. `dim_puente_aportador` es el crosswalk tienda-sku-ndf de
Knobloch (grano `tienda_key`, `sku`, `ndf_id`), también aparte de
`silver.precios`. Su `sku` va a 15 dígitos (`trim` + relleno con
ceros: Ahorro y Farmalisto lo traen relleno con espacios) y se cruza contra
`dim_producto.sku_cruce`, una columna temporal también a 15 dígitos (se le quitan antes
los ceros a la izquierda: San Pablo escribe su sku con relleno a 18).

## Por qué un producto tiene `ndf_id` y otro no

El entity resolution asigna a cada producto de tienda su presentación del
catálogo NDF. Tres métodos, en este orden de precedencia; uno posterior
solo llena lo que los anteriores dejaron vacío y nunca pisa una
asignación (`match_method` dice cuál fue):

| `match_method` | Cómo | Precisión | Productos | NDF nuevos |
| --- | --- | --- | --- | --- |
| `aportadores` | El sku del producto está en el crosswalk de Knobloch de su tienda con un solo `ndf_id`. | 0.990 (auditoría manual) | 83,510 | 26,000 |
| `ean_cruzado` | El sku es un código de barras (8+ dígitos) que otra tienda sí tiene en el crosswalk, con un solo `ndf_id`. | 0.994 (`assert_dim_producto_ean_precision`) | 13,040 | 1,098 |
| `vectorial` | El texto del producto y el de la presentación NDF están cerca en el espacio de embeddings y la marca coincide (regla abajo). | ~0.96 FARMA, ~0.85 NO FARMA (calibración); ~0.98 / ~0.94 en tiendas sin crosswalk | 6,107 | 845 |
| NULL | Ninguno lo resolvió. | — | 137,743 | — |

Corte 2026-09-24: 102,657 de 240,400 productos con `ndf_id` (42.7%; 86.9%
sin el marketplace de walmart y aurrera) y 27,943 de 180,914 NDF con al
menos un producto (15.5%). Las dos métricas se leen así, por método, en
`dim_producto`. El conteo `vectorial` varía unas decenas entre
reconstrucciones del índice: `TREE_AH` es búsqueda aproximada y un índice
nuevo parte el espacio distinto (tras recrearlo en ALD-99 quedó en 6,075
productos y 27,934 NDF en total, -0.5%).

**Los cruces por código** (`int_producto`). El sku del puente va a 15
dígitos (`trim` + relleno: Ahorro y Farmalisto lo traen con espacios) y se
compara contra `sku_cruce`, una columna temporal de `int_producto` también a 15
dígitos (sin ceros a la izquierda antes de rellenar: San Pablo escribe su
sku a 18). Un sku con dos `ndf_id` en el puente es ambiguo y no se asigna.
El EAN exige 8+ dígitos porque por debajo los códigos son internos de cada
tienda y colisionan (precisión 0-17%). Soriana, alsuper y similares no
tienen código común con el crosswalk: solo les llega el vectorial.

**El vectorial, de punta a punta** (`precios_ml`):

1. **Texto.** Del lado tienda, `dim_producto.descripcion` tal cual
   (`int_texto_er_tienda`). Del lado catálogo, `presentacion` con sus
   abreviaturas expandidas (`TABL` → `TABLETAS`, seed `abreviaturas_ndf`,
   `int_ndf_presentacion_expandida`): es la variante `v4` del var
   `variante_ndf`. `int_texto_er` junta los dos lados sin duplicar textos.
2. **Banco.** `emb_texto` guarda un vector (Gemini, 768 dimensiones) por
   hash del texto, incremental. Un rebuild de gold no vuelve a pagar la
   API; **nunca se corre con `--full-refresh`**. Tiene los vectores de `v1`
   y `v4` (452,556).
3. **Vectores por entidad.** `emb_producto` (240,400) y `emb_ndf`
   (180,914), incrementales con `merge` por llave: una carga nueva solo
   inserta o actualiza lo que cambió de texto, sin recrear la tabla.
   `emb_ndf`, la base de la búsqueda, lleva un índice `TREE_AH` que su
   `post_hook` crea si no existe. Si la tabla se recrea (`--full-refresh`),
   el índice cae a 0% de cobertura y tarda ~10 min en volver; mientras tanto la búsqueda es por
   fuerza bruta. Los tests `assert_emb_*_cobertura` fallan si algún
   producto o NDF no tiene el vector de su texto vigente.
4. **Búsqueda.** `int_candidatos_producto`: cada producto busca sus 10 NDF
   más cercanos (distancia coseno). Antes de buscar emite un warning si
   el índice de `emb_ndf` no cubre el 100%. El NDF correcto está entre los 10 en
   el 85.13% de los productos con verdad conocida.
5. **Decisión.** `int_match_ndf` toma el candidato 1 y decide:
   - `sin_match` si alguna palabra de la marca del NDF no aparece en la
     descripción, o si la distancia supera `tau_farma` (0.10) /
     `tau_no_farma` (0.04) según la división del NDF;
   - `vectorial` si además el segundo candidato queda al menos `delta_min`
     (0.008) más lejos, las magnitudes (dosis, volumen, piezas) cuadran y
     la tienda/división no está en `cuarentena_forzada`;
   - `cuarentena` en otro caso.
6. **Gold.** `dim_producto` toma `vectorial` con su `ndf_distancia`.
   `ndf_cuarentena` (silver) guarda los 2,916 productos en `cuarentena` con
   sus 10 candidatos y los dos textos lado a lado; ahí entra el método 3
   (un LLM elige uno de los 10 o ninguno). El test
   `assert_dim_producto_reconcilia_cuarentena` asegura que todo producto
   sin `ndf_id` está en `ndf_cuarentena` o fue `sin_match`.

**Por qué esa regla.** La marca es la señal que separa aciertos de
errores: sin ella la precisión ronda 0.5, con ella la distancia puede
aflojarse sin perder precisión. Los umbrales y su porqué están en
`dbt_project.yml` y en el docstring de `int_match_ndf`; se calibraron
sobre la mitad de los productos con crosswalk (`producto_split_aportadores`,
la otra mitad es holdout intocado) con la vista `rev_er_calibracion`, y se
auditaron a mano 208 productos de tiendas sin crosswalk
(`entity_resolution/auditar_huerfanos.py`). Los genéricos (`PARACETAMOL GI
ALL`) no pasan la regla porque la tienda no escribe el laboratorio: son
trabajo del método 3.

**Qué hay en los 134,827 `sin_match`.** ~112 mil ni tienen la marca de su
candidato ni están cerca de él: en su mayoría no existen en el catálogo
NDF (marketplace no farmacéutico de walmart y aurrera, abarrotes). 17,938
tienen la marca pero están lejos y 4,809 están cerca sin la marca: junto
con la cuarentena, ~25,600 productos son el universo del método 3.

**Volver a `v1`.** Cambiar `variante_ndf: v1` en `dbt_project.yml`. Sus
vectores siguen en el banco, así que no se paga la API. `dbt run --select
emb_ndf` actualiza por `merge` las 180,914 filas (todos los hashes
cambian); esperar a que su índice vuelva al 100% y luego construir
`int_candidatos_producto+` y `ndf_cuarentena`. Los `tau` vigentes están calibrados para `v4`: con `v1`
hay que recalibrarlos (los de `v1` sin guarda eran 0.08 / 0.035).

## Carga de un mes nuevo

Todo lo de dbt corre con un solo `dbt build`; los pasos fuera de dbt son
los de `load/`. En orden:

1. `load/`: `cli.py ingesta` (CSV del mes a raw y bronce) y, si cambió el
   catálogo NDF o el crosswalk, `cli.py catalogos` / `catalogos-puente`.
   Las external tables ven los archivos nuevos al instante.
2. `dbt build`. En el orden del DAG: silver y `int_producto` suman los
   productos nuevos con sus cruces por código; `emb_texto` embebe los
   textos que el banco no tiene (hasta `lote_embeddings`, 50,000 por
   corrida); `emb_producto`/`emb_ndf` entran por `merge`;
   `int_candidatos_producto` busca, `int_match_ndf` decide y
   `dim_producto` / `ndf_cuarentena` reciben el resultado. Un NDF nuevo
   pasa por el seed de abreviaturas sin tocar nada; una tienda nueva no
   necesita configuración (solo `cuarentena_forzada` nombra tiendas).
3. Si fallan `assert_emb_*_cobertura`, el banco quedó a medias (más de
   50,000 textos nuevos): repetir `dbt build` hasta que pasen.
4. Si `int_candidatos_producto` avisa que el índice de `emb_ndf` está en
   0% o no existe, esperar ~10 min y volver a construir
   `int_candidatos_producto+`. Con unos miles de filas sin indexar no hace
   falta.

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
