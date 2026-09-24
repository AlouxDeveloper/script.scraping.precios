{#
    Cobertura por producto del catálogo completo (ALD-90), reporte de
    cierre de la fase: de los ~240,400 `producto_key`, cuáles reciben
    `ndf_id` y por qué método. Grano `producto_key`, gemela de
    `rev_er_cobertura_ndf` -ver su docstring para qué métodos existen hoy
    y por qué `aportadores` no se pisa con `vectorial`.

    El desglose de negocio -farmacias puras contra supermercados- es por
    `tienda_key`, no una columna calculada aquí: se lee agregando esta
    vista por `tienda_key` (ver el cierre de ALD-90 para la interpretación
    escrita de esos números, que no se repite en cada corrida).
#}
{{ config(materialized='view') }}

select
    dim_producto.producto_key,
    dim_producto.tienda_key,
    case
        when dim_producto.match_method in ('aportadores', 'ean_cruzado')
            then dim_producto.match_method
        when int_match_ndf.decision = 'vectorial' then 'vectorial'
    end as metodo,
    dim_producto.match_method is not null
        or int_match_ndf.decision = 'vectorial' as tiene_match
from {{ ref('int_producto') }} as dim_producto
left join {{ ref('int_match_ndf') }} as int_match_ndf
    on int_match_ndf.producto_key = dim_producto.producto_key
