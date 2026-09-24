{#
    Texto del catálogo NDF listo para vectorizar (ver ALD-64), grano
    `ndf_id`. `view`, no `table`: es composición de texto sobre 180,914
    filas, no vale la pena materializarla -lo caro (los embeddings) vive
    aparte, en `precios_ml`, y ese banco sí es el que no se recalcula solo.

    Renombrado de `int_texto_er` a `int_texto_er_ndf` en ALD-61: ese nombre
    quedó libre para la vista combinada (`producto` + `ndf`, deduplicada
    por hash) que consume el banco de embeddings.

    `hash_texto` usa `hash_texto_embedding` -no `dbt_utils.generate_surrogate_key`
    a secas- para que sea la misma llave que usa `int_texto_er`: dos vistas
    calculando el hash distinto del mismo texto sería un bug esperando a
    pasar. También confirma, sin abrir el macro `texto_er_ndf`, que
    `variante_ndf` está llegando: correr este modelo con
    `--vars '{variante_ndf: v2}'` produce un conjunto de hashes distinto al
    de v1, porque el texto que se hashea cambió.

    El join con `int_ndf_presentacion_expandida` es incondicional aunque
    solo `v4` lo use: un `ref()` dentro de un `if` sobre un var deja el DAG
    dependiendo de con qué vars se parseó. Solo se trae
    `presentacion_expandida` para que las columnas de `dim_ndf` que usa
    el macro sigan sin ambigüedad.
#}
{{ config(materialized='view') }}

select
    ndf_id,
    {{ texto_er_ndf() }} as texto,
    {{ hash_texto_embedding(texto_er_ndf()) }} as hash_texto
from {{ ref('dim_ndf') }}
inner join (
    select ndf_id, presentacion_expandida
    from {{ ref('int_ndf_presentacion_expandida') }}
) using (ndf_id)
