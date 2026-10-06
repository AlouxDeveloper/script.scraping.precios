{#
    Compone el texto del catálogo NDF que se vectoriza en el entity
    resolution (ver ALD-64). Vive en un macro y no repetido en
    `int_texto_er_ndf` para que cambiar `variante_ndf` cambie el texto en
    un solo lugar.

    `v1` (default) es la hipótesis de trabajo: `presentacion` ya es, en la
    práctica, `producto || ' ' || descripcion` -verificado contra
    `match_puente_producto.csv`, donde "PALMERS" + "CRA FAC HIDRA AGUA
    COCO&AC HIAL 50GR" aparece como una sola presentación- así que ya trae
    marca y presentación en un solo campo, al grano del `ndf_id`. ALD-64
    midió además `v2` (+ laboratorio) y `v3` (+ forma farmacéutica y
    molécula) por solapamiento léxico: las dos empeoraban y se borraron en
    ALD-99.

    `v4` (ALD-94) es `presentacion` con las abreviaturas del catálogo
    expandidas (`TABL` -> `TABLETAS`), de `int_ndf_presentacion_expandida`.
    Es la variante activa en `dbt_project.yml`; volver a `v1` reutiliza
    sus vectores del banco sin volver a pagar la API.
#}
{% macro texto_er_ndf() %}
    {%- set variante = var('variante_ndf', 'v1') -%}
    {%- if variante == 'v1' -%}
        presentacion
    {%- elif variante == 'v4' -%}
        presentacion_expandida
    {%- else -%}
        {{ exceptions.raise_compiler_error(
            "texto_er_ndf: variante_ndf desconocida '" ~ variante
            ~ "'. Usa v1 o v4."
        ) }}
    {%- endif -%}
{% endmacro %}
