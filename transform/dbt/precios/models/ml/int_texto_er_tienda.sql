{#
    Texto de tienda listo para vectorizar (ver ALD-85). Gemelo de
    `int_texto_er` (catálogo NDF). `view`, no `table` -misma razón: es
    composición de texto sobre 240,400 filas, no vale la pena
    materializarla; lo caro son los embeddings, aparte, en `precios_ml`.

    `hash_texto` confirma que `variante_tienda` está llegando, igual que
    en `int_texto_er`: correr este modelo con
    `--vars '{variante_tienda: t2}'` produce un conjunto de hashes
    distinto al de t1.
#}
{{ config(materialized='view') }}

select
    producto_key,
    {{ texto_er_tienda('descripcion') }} as texto,
    {{ dbt_utils.generate_surrogate_key([texto_er_tienda('descripcion')]) }} as hash_texto
from {{ ref('dim_producto') }}
