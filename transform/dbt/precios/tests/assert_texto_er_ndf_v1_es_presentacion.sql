{#
    Fija el default de texto_er_ndf.sql: sin `variante_ndf` en vars, v1 debe
    ser exactamente `presentacion`, columna por columna, para las 180,914
    filas de dim_ndf -no una aproximación. Si esto falla, o el macro cambió
    de default sin querer, o int_texto_er dejó de leer la variante correcta.
#}

select
    int_texto_er_ndf.ndf_id,
    int_texto_er_ndf.texto,
    dim_ndf.presentacion
from {{ ref('int_texto_er_ndf') }} as int_texto_er_ndf
inner join {{ ref('dim_ndf') }} as dim_ndf
    on dim_ndf.ndf_id = int_texto_er_ndf.ndf_id
where int_texto_er_ndf.texto is distinct from dim_ndf.presentacion
