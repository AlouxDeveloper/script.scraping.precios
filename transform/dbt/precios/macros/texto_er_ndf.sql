{#
    Compone el texto del catálogo NDF que se vectoriza en el entity
    resolution (ver ALD-64). Vive en un macro y no repetido en
    `int_texto_er` para poder medir las tres variantes sin duplicar SQL:
    cambiar `variante_ndf` cambia el texto en un solo lugar.

    `v1` (default) es la hipótesis de trabajo: `presentacion` ya es, en la
    práctica, `producto || ' ' || descripcion` -verificado contra
    `match_puente_producto.csv`, donde "PALMERS" + "CRA FAC HIDRA AGUA
    COCO&AC HIAL 50GR" aparece como una sola presentación- así que ya trae
    marca y presentación en un solo campo, al grano del `ndf_id`. `v2` y
    `v3` existen para descartarlas con un número (solapamiento léxico
    contra la descripción de tienda, y después la métrica vectorial), no
    con una opinión.

    Este default **solo cambia si la medición lo contradice** -no por
    preferencia de quien edite este archivo después.

    ALD-67 cerró la comparación sin correr el barrido vectorial completo:
    el solapamiento léxico de ALD-64 ya era contundente (`v1` gana claro,
    `v2`/`v3` empeoran) y no justificó el costo de embeber el catálogo
    completo dos veces más solo para confirmarlo con `rev_er_metricas`.
    Sigue siendo la mejor evidencia disponible, no la medición vectorial
    original que pedía el issue.
#}
{% macro texto_er_ndf() %}
    {%- set variante = var('variante_ndf', 'v1') -%}
    {%- if variante == 'v1' -%}
        presentacion
    {%- elif variante == 'v2' -%}
        -- Prueba si el laboratorio ayuda o mete ruido: muchas descripciones
        -- de tienda no nombran al fabricante, y una palabra que solo
        -- aparece en un lado desplaza el vector sin aportar señal.
        producto || ' ' || descripcion || ' ' || laboratorio
    {%- elif variante == 'v3' -%}
        -- Prueba si forma_farmaceutica_n3 y molecula aportan por encima de
        -- lo que ya dice presentacion. forma_farmaceutica_n3 es una de las
        -- columnas cuya semántica sigue pendiente del glosario con
        -- Knobloch -si v3 gana, hay que confirmar su significado antes de
        -- fijarla, no asumirlo por el nombre de la columna.
        presentacion || ' ' || forma_farmaceutica_n3 || ' ' || molecula
    {%- else -%}
        {{ exceptions.raise_compiler_error(
            "texto_er_ndf: variante_ndf desconocida '" ~ variante
            ~ "'. Usa v1, v2 o v3."
        ) }}
    {%- endif -%}
{% endmacro %}
