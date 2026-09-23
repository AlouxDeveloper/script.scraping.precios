{#
    Guarda de decisión del entity resolution vectorial (ALD-66): si un
    candidato NDF↔producto, además de estar cerca en el embedding, es
    recíproco y no tiene una magnitud declarada que contradiga a la otra.

    Compone `es_reciproco` -el producto y el NDF se eligieron mutuamente
    como mejor candidato- con `guarda_magnitudes` (ALD-73, extraída de
    aquí para poder aplicarse sola en `int_match_ndf`, antes de elegir el
    mejor candidato, no después).
#}
{% macro pasa_guardas(atributos_producto, atributos_ndf, es_reciproco) %}
    {{ es_reciproco }}
    and {{ guarda_magnitudes(atributos_producto, atributos_ndf) }}
{% endmacro %}
