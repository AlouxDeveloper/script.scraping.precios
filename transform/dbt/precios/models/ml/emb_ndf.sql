{#
    Catálogo NDF completo vectorizado (ALD-70): un vector por `ndf_id`,
    resuelto desde el banco `emb_texto` por el hash del texto de catálogo
    (`int_texto_er_ndf`, variante `variante_ndf`). Es la base de
    `int_candidatos_producto` y lleva índice `TREE_AH` (180,914 vectores,
    ~1.1 GB).

    Incremental con `merge` por `ndf_id` (ALD-99): recrear la tabla deja
    el índice en 0% de cobertura ~10 min y la búsqueda que corre justo
    después cae a fuerza bruta. Un catálogo nuevo inserta los NDF nuevos y actualiza los que
    cambiaron de texto; cambiar `variante_ndf` cambia todos los hashes y
    actualiza la tabla entera, que es lo esperado.

    A diferencia de los productos, un NDF sí puede salir del catálogo (es
    un snapshot de reemplazo): el `post_hook` borra esos huérfanos, o
    `int_candidatos_producto` seguiría proponiendo un `ndf_id` que
    `dim_ndf` ya no tiene. Después crea el índice si no existe
    (`macros/indice_vectorial.sql`).

    `INNER JOIN` contra `emb_texto` y cobertura vigilada por
    `assert_emb_ndf_cobertura`, ver el docstring de `emb_producto`.
#}
{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key='ndf_id',
        on_schema_change='append_new_columns',
        post_hook=[
            "delete from {{ this }} where ndf_id not in (select ndf_id from {{ ref('dim_ndf') }})",
            "{{ indice_vectorial('emb_ndf_idx', ['ndf_id']) }}",
        ]
    )
}}

select
    n.ndf_id,
    x.hash_texto as texto_hash,
    b.embedding
from {{ ref('dim_ndf') }} as n
inner join {{ ref('int_texto_er_ndf') }} as x
    on x.ndf_id = n.ndf_id
inner join {{ ref('emb_texto') }} as b
    on b.texto_hash = x.hash_texto
{% if is_incremental() %}
where not exists (
    select 1
    from {{ this }} as actual
    where actual.ndf_id = n.ndf_id
        and actual.texto_hash = x.hash_texto
)
{% endif %}
