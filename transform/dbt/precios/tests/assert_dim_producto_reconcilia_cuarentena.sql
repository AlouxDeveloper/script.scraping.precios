{#
    Reconciliación de ALD-97: todo producto sin `ndf_id` en `dim_producto`
    está en `ndf_cuarentena` o es `sin_match` en `int_match_ndf`, nunca en
    los dos ni en ninguno; y ningún producto con `ndf_id` sigue en
    cuarentena. Un `vectorial` sin `ndf_id` sería un hueco del coalesce.
    Los duplicados dentro de la cuarentena los atrapa su test de grano.
#}
with cuarentena as (

    select distinct producto_key
    from {{ ref('ndf_cuarentena') }}

)

select
    dim_producto.producto_key,
    dim_producto.ndf_id,
    int_match_ndf.decision,
    cuarentena.producto_key is not null as en_cuarentena
from {{ ref('dim_producto') }} as dim_producto
left join {{ ref('int_match_ndf') }} as int_match_ndf
    on int_match_ndf.producto_key = dim_producto.producto_key
left join cuarentena
    on cuarentena.producto_key = dim_producto.producto_key
where int_match_ndf.decision is null
    or (cuarentena.producto_key is not null) != (
        dim_producto.ndf_id is null and int_match_ndf.decision = 'cuarentena'
    )
    or (dim_producto.ndf_id is null and int_match_ndf.decision = 'vectorial')
