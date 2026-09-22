{#
    Texto del catálogo NDF listo para vectorizar (ver ALD-64). `view`, no
    `table`: es composición de texto sobre 180,914 filas, no vale la pena
    materializarla -lo caro (los embeddings) vive aparte, en `precios_ml`,
    llaveado por `hash_texto`, y ese banco sí es el que no se recalcula
    solo.

    `hash_texto` es lo que confirma, sin abrir el macro, que
    `variante_ndf` está llegando: correr este modelo con
    `--vars '{variante_ndf: v2}'` produce un conjunto de hashes distinto al
    de v1, porque el texto que se hashea cambió.
#}
{{ config(materialized='view') }}

select
    ndf_id,
    {{ texto_er_ndf() }} as texto,
    {{ dbt_utils.generate_surrogate_key([texto_er_ndf()]) }} as hash_texto
from {{ ref('dim_ndf') }}
