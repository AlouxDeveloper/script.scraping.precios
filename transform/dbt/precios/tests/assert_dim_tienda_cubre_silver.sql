{#
    Falla si alguna `tienda` de `precios_silver.precios` no tiene fila en
    `dim_tienda`: el catálogo nuevo tiene que cruzar con todo el histórico
    ya cargado en BigQuery. Es la garantía de ALD-46.
#}
select distinct p.tienda
from {{ ref('precios') }} as p
left join {{ ref('dim_tienda') }} as t
    on p.tienda = t.tienda_slug
where t.tienda_key is null
