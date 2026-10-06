{#
    Banco de embeddings (ALD-62). Llaveado por `texto_hash`, no por
    `producto_key` ni `ndf_id`: `dim_producto` es `table` con full refresh y
    recalcula esas llaves en cada build; colgar el banco del hash del texto
    es lo que deja sobrevivir los vectores ya pagados a una reconstrucción
    completa de gold (ver `hash_texto_embedding.sql`).

    `modelo`/`dimension`/`task_type` van como columna real -no solo dentro
    del hash- porque son lo que distingue una generación de vectores de
    otra sobre el mismo `texto_hash` cuando conviven dos generaciones
    (`DELETE ... WHERE modelo = '...'` para regenerar una sola, ver
    `sin_full_refresh.sql`).

    Carga por lotes: `pendientes` es el anti-join contra lo ya generado más
    `limit lote_embeddings` (var, default 50,000). Igual que la
    reanudación por `set` de URLs de los scrapers -las corridas largas se
    interrumpen- así que se re-ejecuta `dbt run --select emb_texto` hasta
    que `pendientes` sale vacío.

    `AI.GENERATE_EMBEDDING` exige una columna `content` STRING en su
    segundo argumento (confirmado contra docs.cloud.google.com, no contra
    memoria); de ahí el alias `texto as content`. Devuelve `embedding`
    NULL cuando `status` trae un error de la API -el `where status = ''`
    filtra esas filas antes del merge: quedan sin `texto_hash` en el banco,
    así que el anti-join de la próxima corrida las vuelve a intentar en
    vez de dejarlas fallidas para siempre.
#}
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='texto_hash',
    on_schema_change='append_new_columns'
) }}
{{ sin_full_refresh() }}

{%- set modelo = var('modelo_embedding', 'emb_gemini') -%}
{%- set dimension = var('dimension_embedding', 768) -%}
{%- set task_type = var('task_type_embedding', 'SEMANTIC_SIMILARITY') -%}

with pendientes as (

    select
        origen.texto_hash,
        origen.texto
    from {{ ref('int_texto_er') }} as origen
    {% if is_incremental() %}
    where not exists (
        select 1
        from {{ this }} as generado
        where generado.texto_hash = origen.texto_hash
    )
    {% endif %}
    limit {{ var('lote_embeddings', 50000) }}

),

generado as (

    select *
    from AI.GENERATE_EMBEDDING(
        MODEL `{{ target.project }}.precios_ml.{{ modelo }}`,
        (
            select texto_hash, texto as content
            from pendientes
        ),
        STRUCT(
            '{{ task_type }}' as task_type,
            {{ dimension }} as output_dimensionality
        )
    )

)

select
    texto_hash,
    content as texto,
    '{{ modelo }}' as modelo,
    {{ dimension }} as dimension,
    '{{ task_type }}' as task_type,
    embedding,
    current_timestamp() as generado_en
from generado
where status = ''
