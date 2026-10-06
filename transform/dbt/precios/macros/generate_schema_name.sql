{#
    Devuelve el schema literal en vez del `<schema_del_perfil>_<custom>` que
    dbt compone por defecto. Sin esto, un modelo con `+schema: precios_gold`
    escribiría en `precios_silver_precios_gold`.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
