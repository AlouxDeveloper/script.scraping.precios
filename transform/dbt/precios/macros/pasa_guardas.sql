{#
    Guarda de decisión del entity resolution vectorial (ALD-66): si un
    candidato NDF↔producto, además de estar cerca en el embedding, es
    reciproco y no tiene una magnitud declarada que contradiga a la otra.

    Reciprocidad primero -`es_reciproco` (ver `int_candidatos_ndf.sql`): el
    producto y el NDF se eligieron mutuamente como mejor candidato.

    Magnitudes después, una por atributo de `extraer_atributos` (ALD-69):
    aprueba si CUALQUIERA de los dos lados no declaró el atributo -NULL es
    "no declarado", no cero, y la ausencia no se penaliza-, y exige
    igualdad exacta cuando ambos lados sí lo declararon. Esta es la regla
    de aplicación que el docstring de `extraer_atributos` deja pendiente
    ("¿penaliza discordancia, ignora ausencia? vive en el modelo que usa
    este macro").

    Recibe los dos STRUCT ya calculados (`atributos_producto`,
    `atributos_ndf` de `int_candidatos_ndf`) y el nombre de la columna
    `es_reciproco` -no vuelve a llamar `extraer_atributos` ni a tocar el
    texto crudo.
#}
{% macro pasa_guardas(atributos_producto, atributos_ndf, es_reciproco) %}
    {{ es_reciproco }}
    and (
        {{ atributos_producto }}.dosis_mg is null
        or {{ atributos_ndf }}.dosis_mg is null
        or {{ atributos_producto }}.dosis_mg = {{ atributos_ndf }}.dosis_mg
    )
    and (
        {{ atributos_producto }}.volumen_ml is null
        or {{ atributos_ndf }}.volumen_ml is null
        or {{ atributos_producto }}.volumen_ml = {{ atributos_ndf }}.volumen_ml
    )
    and (
        {{ atributos_producto }}.masa_g is null
        or {{ atributos_ndf }}.masa_g is null
        or {{ atributos_producto }}.masa_g = {{ atributos_ndf }}.masa_g
    )
    and (
        {{ atributos_producto }}.piezas is null
        or {{ atributos_ndf }}.piezas is null
        or {{ atributos_producto }}.piezas = {{ atributos_ndf }}.piezas
    )
{% endmacro %}
