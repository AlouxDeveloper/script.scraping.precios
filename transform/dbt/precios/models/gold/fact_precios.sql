{#
    Tabla de hechos de precios (Kimball). Grano `(producto_key, fecha_key)`:
    un precio observado por producto y día. Grano medido en ALD-37.

    Dos medidas y nada derivado. El porcentaje de descuento y el precio
    efectivo se calculan en la capa de consumo, no aquí. `precio_oferta` llega NULL
    -no 0- desde silver (ALD-44): con el centinela `0` vigente, cualquier
    `MIN()` o `AVG()` sobre la columna devolvía cero.

    Se llama `precio_lista`, no `precio`: renombrarla solo en la fact
    rompería la continuidad con silver sin ganar nada.

    `tienda_key` va denormalizada aunque ya viva dentro de `producto_key`:
    filtrar por tienda es el corte más frecuente y así no exige joinear
    `dim_producto`.

    Físico: particionada por `fecha_key` a grano día, clusterizada por
    `tienda_key` y `producto_key`. Sin `require_partition_filter`: a ~925
    mil filas y menos de 1 GB no ahorra nada material y rompe las
    herramientas de BI que no inyectan filtro de fecha.
#}
{{
    config(
        materialized='table',
        partition_by={
            'field': 'fecha_key',
            'data_type': 'date',
            'granularity': 'day'
        },
        cluster_by=['tienda_key', 'producto_key']
    )
}}

with precios as (

    select
        tienda,
        sku,
        fecha_captura as fecha_key,
        url_producto,
        precio_lista,
        precio_oferta
    from {{ ref('precios') }}

),

con_llaves as (

    select
        dim_producto.producto_key,
        dim_tienda.tienda_key,
        precios.fecha_key,
        precios.url_producto,
        precios.precio_lista,
        precios.precio_oferta
    from precios
    inner join {{ ref('dim_tienda') }} as dim_tienda
        on precios.tienda = dim_tienda.tienda_slug
    inner join {{ ref('dim_producto') }} as dim_producto
        on dim_tienda.tienda_key = dim_producto.tienda_key
        and precios.sku = dim_producto.sku

),

-- Dedup. Silver no es único en `(producto_key, fecha_key)`: ALD-37 midió
-- 1,301 combos con más de una fila y 17,584 filas de exceso -re-scrapeos
-- con texto o imagen distinta, y 68 combos con precio ambiguo el mismo
-- día-. Gana el precio de lista más bajo observado ese día; el desempate
-- por `precio_oferta` y luego `url_producto` cierra el orden y hace la
-- elección determinística entre builds idénticos.
numerado as (

    select
        *,
        row_number() over (
            partition by producto_key, fecha_key
            order by precio_lista asc, precio_oferta asc, url_producto asc
        ) as rn
    from con_llaves

)

select
    producto_key,
    tienda_key,
    fecha_key,
    precio_lista,
    precio_oferta
from numerado
where rn = 1
