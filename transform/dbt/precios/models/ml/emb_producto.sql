{#
    Lado tienda vectorizado (ALD-71): un vector por `producto_key`,
    resuelto desde el banco `emb_texto` por el hash del texto de tienda
    (`int_texto_er_tienda`). Es la tabla de consulta de
    `int_candidatos_producto` (~240,400 vectores). Sin índice vectorial:
    el índice sirve a la tabla base de la búsqueda (`emb_ndf`), y esta es
    la de consulta. El que tenía servía a la búsqueda NDF→producto de la
    fase Sanfer y se quitó en ALD-99.

    **Incremental con `merge` por `producto_key` (ALD-99)**, no `table`.
    Con `merge` un mes nuevo solo inserta los productos nuevos y
    actualiza los que cambiaron de texto (otro `texto_hash`), en vez de
    reescribir las 240,400 filas. Es viable porque `producto_key` es un hash estable de
    `(tienda_key, sku)`. `--full-refresh` es seguro aquí: no llama a la
    API, a diferencia de `emb_texto`.

    `INNER JOIN` contra `emb_texto`: un producto cuyo texto el banco aún
    no tiene no entra, y la siguiente corrida lo vuelve a intentar porque
    su `(producto_key, texto_hash)` sigue sin estar aquí. Lo vigila
    `assert_emb_producto_cobertura`. Antes era `LEFT JOIN` con
    `not_null(embedding)`, pero BigQuery guarda un ARRAY NULL como arreglo
    vacío y ese test nunca podía fallar.
#}
{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key='producto_key',
        on_schema_change='append_new_columns'
    )
}}

select
    p.producto_key,
    p.tienda_key,
    x.hash_texto as texto_hash,
    b.embedding
from {{ ref('int_producto') }} as p
inner join {{ ref('int_texto_er_tienda') }} as x
    on x.producto_key = p.producto_key
inner join {{ ref('emb_texto') }} as b
    on b.texto_hash = x.hash_texto
{% if is_incremental() %}
where not exists (
    select 1
    from {{ this }} as actual
    where actual.producto_key = p.producto_key
        and actual.texto_hash = x.hash_texto
)
{% endif %}
