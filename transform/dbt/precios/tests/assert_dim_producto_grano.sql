{#
    Falla si el conteo de filas de `dim_producto` no coincide con
    `count(distinct (tienda, sku))` de `precios`. Es el grano medido en
    ALD-37 (159,890 productos): la dimensión no debe perder ni inventar
    productos al traducir el slug a `tienda_key`.
#}
with esperado as (

    select count(distinct format('%s|%s', tienda, sku)) as n
    from {{ ref('precios') }}

),

obtenido as (

    select count(*) as n
    from {{ ref('dim_producto') }}

)

select esperado.n as esperado, obtenido.n as obtenido
from esperado
cross join obtenido
where esperado.n != obtenido.n
