{#
    Texto de tienda listo para vectorizar (ver ALD-85), grano
    `producto_key`. Gemelo de `int_texto_er_ndf` (catálogo NDF). `view`, no
    `table` -misma razón: es composición de texto sobre 240,400 filas, no
    vale la pena materializarla; lo caro son los embeddings, aparte, en
    `precios_ml`.

    `hash_texto` usa `hash_texto_embedding` -misma llave que
    `int_texto_er_ndf` y la vista combinada `int_texto_er` (ALD-61)- y
    confirma que `variante_tienda` está llegando: correr este modelo con
    `--vars '{variante_tienda: t2}'` produce un conjunto de hashes
    distinto al de t1.
#}
{{ config(materialized='view') }}

select
    producto_key,
    {{ texto_er_tienda('descripcion') }} as texto,
    {{ hash_texto_embedding(texto_er_tienda('descripcion')) }} as hash_texto
from {{ ref('dim_producto') }}
