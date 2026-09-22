{#
    Catálogo NDF completo vectorizado (ALD-70). `table`, no `view`: el
    índice vectorial solo se construye sobre tablas. Va el catálogo
    entero (180,914, ~1.1 GB), no el recorte Sanfer (~1,400, 8.6 MB) -por
    debajo del mínimo de 10 MB de tabla base que exige `TREE_AH`, el
    índice se deshabilitaría solo (`BASE_TABLE_TOO_SMALL`). Por eso la
    fase Sanfer no usa esta tabla como base: usa `emb_producto` (ALD-71) y
    corre los 1,400 vectores de Sanfer como conjunto de consulta. Esta
    tabla es la base de la fase del catálogo completo, donde la búsqueda
    se invierte a producto→NDF.

    `LEFT JOIN` contra `emb_texto`, no `INNER`, gemelo de `emb_producto`:
    un `ndf_id` sin vector sobrevive como NULL y revienta el
    `not_null(embedding)` en vez de desaparecer en silencio -señal de que
    el banco está incompleto, no de que el modelo esté mal.

    `ndf_id` único por construcción: `dim_ndf` (grano `ndf_id`) →
    `int_texto_er_ndf` (mismo grano, 1:1) → `emb_texto` (grano
    `texto_hash`, único por `ndf_id` porque `int_texto_er_ndf.hash_texto`
    ya lo es).
#}
{{ config(materialized='table') }}

select
    n.ndf_id,
    b.embedding
from {{ ref('dim_ndf') }} as n
inner join {{ ref('int_texto_er_ndf') }} as x
    on x.ndf_id = n.ndf_id
left join {{ ref('emb_texto') }} as b
    on b.texto_hash = x.hash_texto
