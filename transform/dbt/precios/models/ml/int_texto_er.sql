{#
    Lista de trabajo del banco de embeddings `emb_texto` (ver ALD-61): todo
    texto que hay que vectorizar, de los dos lados, deduplicado por hash.
    `view`, no `table` -es unión y agregación sobre dos vistas que a su vez
    son composición de texto, nada que valga la pena materializar.

    El universo es completo (`int_texto_er_ndf` + `int_texto_er_tienda`
    enteras), no el recorte Sanfer: el total de textos es el mismo de
    todos modos, y así la fase del catálogo completo no vuelve a pagar la
    API. El recorte se filtra aguas abajo, no aquí.

    Grano: `texto_hash`, no `ndf_id` ni `producto_key`. Un mismo texto
    exacto que aparece en dos tiendas -o, en el caso raro, en ambos lados-
    comparte una sola fila y una sola llamada a la API; los modelos que
    consumen el banco resuelven de vuelta a su `ndf_id`/`producto_key` por
    el hash de su propio texto, no al revés. Esa indirección es lo que
    permite reconstruir gold entero sin invalidar el banco.

    `origen` en el caso de que el mismo texto exacto llegue de ambos
    lados: `min(origen)` deja "ndf" antes que "producto" alfabéticamente
    -una regla arbitraria pero determinística, documentada aquí para no
    sorprender a quien la encuentre después. Sí ocurre en el histórico
    real, medido en ALD-61: 157 textos de tienda coinciden carácter por
    carácter con un texto de catálogo y quedan etiquetados "ndf" -por eso
    el conteo de `origen = 'producto'` (151,954) es 157 menor que
    `count(distinct texto)` de `int_texto_er_tienda` sola (152,111).
#}
{{ config(materialized='view') }}

with todos as (

    select texto, 'ndf' as origen
    from {{ ref('int_texto_er_ndf') }}

    union all

    select texto, 'producto' as origen
    from {{ ref('int_texto_er_tienda') }}

)

select
    {{ hash_texto_embedding('texto') }} as texto_hash,
    texto,
    min(origen) as origen
from todos
group by texto
