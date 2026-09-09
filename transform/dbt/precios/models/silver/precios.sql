{#
    Tabla limpia de primera etapa: sin duplicados exactos, con el precio
    de lista resuelto. Materializada como tabla -no vista- porque gold y
    BI la consultan repetidamente y no vale la pena reprocesar el
    histórico completo en cada lectura.

    Sin columnas de linaje ni `en_oferta`: en silver ya no se usan para
    depurar (eso vive en `precios_cuarentena`) y `en_oferta` es
    redundante contra `precio_oferta is not null`. `sku` no necesita
    relleno porque `stg_precios` ya descarta a `precios_cuarentena`
    (motivo `SIN_SKU`) la fila que no lo resuelve.

    `precio_oferta` es NULL cuando no hay descuento real, NO 0. Un
    centinela `0` en una columna numérica se cuela en cualquier `MIN()`
    o `AVG()` de la capa de consumo y de la fact, y el error -precios de
    oferta reportados como cero- no se nota hasta que lo ve el cliente.
    El `0` original sigue disponible en `precios_ext` y en
    `precios_cuarentena` para trazabilidad.

    El porcentaje de descuento y el precio efectivo son derivadas: se
    calculan en la capa de consumo, no aquí. `url_imagen` sí conserva su relleno
    `SIN_IMAGEN`: es un valor legítimo de negocio, no un número que
    contamine una agregación.
#}
{{
    config(
        materialized='table',
        partition_by={
            'field': 'mes',
            'data_type': 'date',
            'granularity': 'month'
        },
        cluster_by=['tienda']
    )
}}

with base as (

    select
        tienda,
        mes,
        fecha_captura,
        url_producto,
        sku,
        producto,
        nombre_norm,
        url_imagen,
        -- si solo llegó un precio, ese es el de lista: sin dos precios no
        -- hay oferta verificable.
        coalesce(precio_lista, precio_oferta) as precio_lista,
        case when precio_lista is not null then precio_oferta end
            as precio_oferta_candidato
    from {{ ref('stg_precios') }}
    where motivo_descarte is null and rn = 1

),

derivadas as (

    select
        *,
        -- la mayoría de las tiendas repite el mismo valor en ambas
        -- columnas del CSV: sin la comparación "< precio_lista" casi
        -- todo el histórico aparecería en oferta. Un precio_oferta mayor
        -- al de lista (error de la tienda) también cae aquí como falso.
        precio_oferta_candidato is not null
            and precio_oferta_candidato < precio_lista as en_oferta
    from base

)

select
    tienda,
    mes,
    fecha_captura,
    url_producto,
    sku,
    producto,
    nombre_norm,
    coalesce(url_imagen, 'SIN_IMAGEN') as url_imagen,
    precio_lista,
    if(en_oferta, precio_oferta_candidato, null) as precio_oferta
from derivadas
