{#
    Falla si el conteo de `fact_precios` no cuadra con silver. La única
    diferencia permitida contra `precios_silver.precios` es la dedup de
    ALD-37: 17,584 filas de exceso colapsadas. Post-dedup el conteo tiene
    que ser exactamente el número de combos `(producto_key, fecha_key)`.
#}
with combos_silver as (

    select count(*) as n
    from (
        select distinct
            dim_producto.producto_key,
            precios.fecha_captura
        from {{ ref('precios') }} as precios
        inner join {{ ref('dim_tienda') }} as dim_tienda
            on precios.tienda = dim_tienda.tienda_slug
        inner join {{ ref('dim_producto') }} as dim_producto
            on dim_tienda.tienda_key = dim_producto.tienda_key
            and precios.sku = dim_producto.sku
    )

),

filas_fact as (

    select count(*) as n
    from {{ ref('fact_precios') }}

)

select combos_silver.n as combos_silver, filas_fact.n as filas_fact
from combos_silver
cross join filas_fact
where combos_silver.n != filas_fact.n
