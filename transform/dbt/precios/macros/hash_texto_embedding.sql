{#
    Llave del banco de embeddings `emb_texto` (ver ALD-56, ALD-60, ALD-61).
    Incluye `modelo`, `dimension` y `task_type` -no solo el texto- porque
    el mismo texto embebido con un modelo, dimensión o task_type distinto
    produce un vector distinto: si el hash fuera solo del texto, una
    regeneración con otro modelo pisaría la fila anterior en vez de
    convivir con ella, y `DELETE ... WHERE modelo = '...'` (la forma
    correcta de regenerar una generación, ver `sin_full_refresh.sql`)
    dejaría de tener sentido -no habría dos generaciones que distinguir.

    Los tres parámetros son `var(...)` y no columnas: hoy son constantes
    (un solo modelo, una sola dimensión, un solo task_type en todo el
    banco), pero vivir en vars y no hardcodeados en el macro es lo que
    permite generar una segunda generación de vectores sin editar SQL.
#}
{% macro hash_texto_embedding(columna_texto) %}
    {%- set modelo = var('modelo_embedding', 'emb_gemini') -%}
    {%- set dimension = var('dimension_embedding', 768) -%}
    {%- set task_type = var('task_type_embedding', 'SEMANTIC_SIMILARITY') -%}
    to_hex(md5(concat(
        '{{ modelo }}', '|', '{{ dimension }}', '|', '{{ task_type }}', '|',
        {{ columna_texto }}
    )))
{% endmacro %}
