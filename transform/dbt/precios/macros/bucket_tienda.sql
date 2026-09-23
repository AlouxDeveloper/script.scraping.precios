{#
    Bucket de estilo de descripción por tienda (ALD-84: A alto solape
    léxico, B bajo solape / default). Genera el `IN (...)` desde
    `var('bucket_tienda_a')` (`dbt_project.yml`, ALD-68) en vez de
    repetir la lista de tiendas a mano en cada modelo que necesita el
    umbral por bucket -hoy solo `int_match_ndf`, pero el criterio es el
    mismo que decide `tau_alto`/`tau_bajo` en los `vars`, así que vive en
    un solo lugar.

    Cualquier tienda que no esté en la lista cae en `'B'` por default
    -incluye las 6 tiendas sin ningún par en el crosswalk y `yza` (n=1):
    ante la duda, el escenario más exigente, no al revés.
#}
{% macro bucket_tienda(tienda_slug_columna) %}
    case
        when {{ tienda_slug_columna }} in (
            {%- for slug in var('bucket_tienda_a') -%}
                '{{ slug }}'{{ "," if not loop.last }}
            {%- endfor -%}
        ) then 'A'
        else 'B'
    end
{% endmacro %}
