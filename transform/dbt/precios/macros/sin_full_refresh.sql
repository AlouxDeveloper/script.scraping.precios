{#
    Aborta la compilación si el modelo que la llama correría con full
    refresh (ver ALD-60). Pensada para `emb_texto` -el banco de
    embeddings-, pero cualquier modelo incremental puede usarla.

    Usa `should_full_refresh()`, no `flags.FULL_REFRESH` directo: la
    bandera de CLI es solo una de las dos formas de disparar un full
    refresh. Un modelo con `{{ config(full_refresh=true) }}` también lo
    fuerza sin que nadie pase `--full-refresh`, y ese caso hay que
    bloquearlo igual -`should_full_refresh()` es la macro que el propio
    adaptador de BigQuery usa para decidir si recrear la tabla
    (`dbt-adapters/macros/materializations/configs.sql`), así que es la
    misma verdad que consulta la materialización, no una reimplementación
    aparte que podría desincronizarse.

    El camino correcto para regenerar `emb_texto` es
    `DELETE FROM precios_ml.emb_texto WHERE modelo = '...'`: borra una
    generación de vectores y deja las demás. Un full refresh recrearía la
    tabla entera y volvería a pagar la API por todo lo que ya estaba.
#}
{% macro sin_full_refresh() %}
    {%- if should_full_refresh() -%}
        {{ exceptions.raise_compiler_error(
            "emb_texto no admite --full-refresh: borraria embeddings ya"
            ~ " pagados. Para regenerar una generacion concreta, borra por"
            ~ " `modelo` con un DELETE explicito."
        ) }}
    {%- endif -%}
{% endmacro %}
