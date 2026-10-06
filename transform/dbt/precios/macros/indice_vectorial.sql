{#
    DDL del índice `TREE_AH` de una tabla de embeddings, para `post_hook`
    (ALD-99). Con `IF NOT EXISTS` no hace nada ni cuesta cuando el índice
    ya existe, que es el caso normal: BigQuery lo conserva aunque dbt
    recree la tabla. Es la red de seguridad para cuando alguien la borra
    o el índice se pierde; antes eso era un paso manual
    (`entity_resolution/sql/indice_emb_ndf.sql`, que queda de referencia).

    La construcción es asíncrona: el DDL solo la registra y tarda ~10 min.
    Mientras tanto `VECTOR_SEARCH` busca por fuerza bruta lo no indexado;
    `avisar_indice_vectorial` lo reporta antes de la búsqueda.
#}
{% macro indice_vectorial(nombre, columnas_storing) %}
    create vector index if not exists {{ nombre }}
    on {{ this }}(embedding)
    storing ({{ columnas_storing | join(', ') }})
    options (index_type = 'TREE_AH', distance_type = 'COSINE')
{% endmacro %}


{#
    Avisa (warning de dbt, no error) si alguna de las tablas base de una
    búsqueda vectorial tiene el índice sin `ACTIVE` o con filas sin
    indexar: esas filas se buscan por fuerza bruta, lo que es correcto
    pero puede ser caro o topar el límite de CPU on-demand (ALD-90). Tras
    una carga incremental normal quedan unos miles sin indexar y el aviso
    es informativo; si dice 0% o que no hay índice, conviene esperar.
    Se llama desde el cuerpo del modelo y no devuelve SQL.
#}
{% macro avisar_indice_vectorial(relaciones) %}
    {%- if execute -%}
        {%- for relacion in relaciones -%}
            {%- set consulta -%}
                select
                    count(*) as n_indices,
                    logical_and(index_status = 'ACTIVE') as activo,
                    min(coverage_percentage) as cobertura_pct,
                    sum(unindexed_row_count) as sin_indexar
                from `{{ relacion.database }}.{{ relacion.schema }}`.INFORMATION_SCHEMA.VECTOR_INDEXES
                where table_name = '{{ relacion.identifier }}'
            {%- endset -%}
            {%- set fila = run_query(consulta).rows[0] -%}
            {%- if fila['n_indices'] == 0 -%}
                {{ exceptions.warn(relacion.identifier ~ " no tiene índice vectorial: la búsqueda será por fuerza bruta completa.") }}
            {%- elif not fila['activo'] or fila['cobertura_pct'] < 100 -%}
                {{ exceptions.warn(
                    relacion.identifier ~ ": índice "
                    ~ ("ACTIVE" if fila['activo'] else "NO ACTIVE")
                    ~ ", cobertura " ~ fila['cobertura_pct'] ~ "%, "
                    ~ fila['sin_indexar'] ~ " filas sin indexar se buscarán por fuerza bruta."
                ) }}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
{% endmacro %}
