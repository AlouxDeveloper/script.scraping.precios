{#
    Recorte Sanfer de `emb_ndf` (ALD-72): el lado de consulta de
    `VECTOR_SEARCH` en `int_candidatos_ndf`, no una base indexada -por eso
    `view` y no `table`, a diferencia de `emb_ndf`/`emb_producto`. `TREE_AH`
    exige 10 MB de tabla base; este recorte pesa ~8.6 MB (ver ALD-56) y de
    cualquier forma el índice va del lado `emb_producto` (ALD-71), no aquí.

    Filtra `emb_ndf` -no repite el join contra `emb_texto`- para no
    duplicar la regla de vectorización: si `emb_ndf` cambia de variante de
    texto, este recorte la hereda solo.
#}
{{ config(materialized='view') }}

select
    emb_ndf.ndf_id,
    emb_ndf.embedding
from {{ ref('emb_ndf') }} as emb_ndf
inner join {{ ref('dim_ndf') }} as dim_ndf
    on dim_ndf.ndf_id = emb_ndf.ndf_id
where upper(dim_ndf.laboratorio) = 'SANFER'
