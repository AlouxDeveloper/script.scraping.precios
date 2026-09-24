{#
    Fija qué texto produce texto_er_ndf.sql según la variante activa, para
    las 180,914 filas de dim_ndf, columna por columna: v1 debe ser
    exactamente `presentacion` y v4 exactamente `presentacion_expandida`
    (ALD-94). Si esto falla, o el macro cambió sin querer, o
    int_texto_er_ndf dejó de leer la variante correcta. v2 y v3 no se
    fijan: se descartaron en ALD-64 y no se usan.
#}
{%- set variante = var('variante_ndf', 'v1') -%}

select
    int_texto_er_ndf.ndf_id,
    int_texto_er_ndf.texto
from {{ ref('int_texto_er_ndf') }} as int_texto_er_ndf
inner join {{ ref('int_ndf_presentacion_expandida') }} as esperado
    on esperado.ndf_id = int_texto_er_ndf.ndf_id
{% if variante == 'v1' %}
where int_texto_er_ndf.texto is distinct from esperado.presentacion
{% elif variante == 'v4' %}
where int_texto_er_ndf.texto is distinct from esperado.presentacion_expandida
{% else %}
where false
{% endif %}
