{#
    Falla si algún `fecha_captura` de `precios` no tiene fila en
    `dim_fecha`: la dimensión tiene que cubrir todo el histórico ya
    cargado. Es la garantía de ALD-47, equivalente al test de cobertura de
    `dim_tienda`.
#}
select distinct p.fecha_captura
from {{ ref('precios') }} as p
left join {{ ref('dim_fecha') }} as f
    on p.fecha_captura = f.fecha_key
where f.fecha_key is null
