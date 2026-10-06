{#
    Normaliza la descripción del producto a una forma comparable con el
    catálogo NDF (sin acentos, dosis/forma/cantidad como texto plano). Solo
    limpia; no descompone en columnas.

    El punto decimal se protege antes de tirar la puntuación: hay 184,645
    puntos en el histórico y muchos son decimales ("0.5 ml"). Borrarlos a
    secas produce "05 ml". El marcador temporal usa solo letras (sin guion
    bajo ni símbolos) para que el paso 4 -que tira todo lo que no sea letra,
    dígito o espacio- lo deje intacto.
#}
{% macro limpiar_texto(columna) %}
    {%- set marcador_decimal = 'qzpuntodecimalqz' -%}
    trim(
        regexp_replace(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(
                            normalize(lower(trim({{ columna }})), NFD),
                            r'\pM', ''
                        ),
                        r'(\d)\.(\d)', r'\1{{ marcador_decimal }}\2'
                    ),
                    r'[^\p{L}\p{N} ]', ' '
                ),
                r'{{ marcador_decimal }}', '.'
            ),
            r' +', ' '
        )
    )
{% endmacro %}
