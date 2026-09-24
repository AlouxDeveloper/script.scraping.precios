{#
    Texto de tienda listo para vectorizar, grano `producto_key`. Gemelo de
    `int_texto_er_ndf` (catálogo NDF). `view`, no `table`: es composición
    de texto sobre 240,400 filas; lo caro son los embeddings, aparte, en
    `precios_ml`.

    El texto es `descripcion` tal cual (ya normalizada por `limpiar_texto`
    y en mayúsculas). ALD-85 midió una variante que recortaba relleno y
    normalizaba magnitudes (`t2`): salió mixta -sube en tiendas verbosas,
    baja en las concisas- y se descartó; el macro que la parametrizaba se
    borró en ALD-99.

    `hash_texto` usa `hash_texto_embedding`, misma llave que
    `int_texto_er_ndf` y la vista combinada `int_texto_er` (ALD-61).
#}
{{ config(materialized='view') }}

select
    producto_key,
    descripcion as texto,
    {{ hash_texto_embedding('descripcion') }} as hash_texto
from {{ ref('int_producto') }}
