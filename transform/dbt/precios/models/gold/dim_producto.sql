{#
    Dimensión de producto de tienda (Kimball). Grano `(tienda_key, sku)`.
    Todo lo que no es el `ndf_id` vectorial se arma en `int_producto` (ver
    su docstring: llave, SCD1, crosswalk y EAN); aquí solo se suma la
    tercera fuente de `ndf_id`.

    Precedencia `aportadores` → `ean_cruzado` → `vectorial` → NULL: el
    vectorial solo llena lo que los dos cruces por código dejaron vacío,
    nunca pisa una asignación previa (su precisión es menor: ~0.96 FARMA,
    ~0.85 NO FARMA contra 0.99). Entra solo `decision = 'vectorial'` de
    `int_match_ndf`; la `cuarentena` no asigna `ndf_id` y va a
    `ndf_cuarentena` para el método 3.

    `ndf_distancia` es la distancia coseno del candidato vectorial, NULL
    cuando el `ndf_id` vino de otro método: esos no tienen distancia y un
    valor ahí haría creer que el crosswalk también es una aproximación.
#}
{{
    config(
        materialized='table',
        cluster_by=['tienda_key']
    )
}}

with vectorial as (

    select producto_key, ndf_id, distancia
    from {{ ref('int_match_ndf') }}
    where decision = 'vectorial'

)

select
    int_producto.producto_key,
    int_producto.tienda_key,
    int_producto.sku,
    coalesce(int_producto.ndf_id, vectorial.ndf_id) as ndf_id,
    case
        when int_producto.match_method is not null
            then int_producto.match_method
        when vectorial.ndf_id is not null then 'vectorial'
    end as match_method,
    if(int_producto.ndf_id is null, vectorial.distancia, null)
        as ndf_distancia,
    int_producto.producto,
    int_producto.descripcion,
    int_producto.url_producto_actual,
    int_producto.url_imagen_actual,
    int_producto.fecha_primera_captura,
    int_producto.fecha_ultima_captura,
    int_producto.dias_observados
from {{ ref('int_producto') }} as int_producto
left join vectorial
    on vectorial.producto_key = int_producto.producto_key
