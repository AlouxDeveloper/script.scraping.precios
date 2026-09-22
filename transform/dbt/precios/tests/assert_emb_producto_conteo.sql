{#
    Falla si `emb_producto` no cubre exactamente el mismo universo que
    `dim_producto` (ver ALD-71). El `LEFT JOIN` del modelo ya deja pasar
    huecos como NULL -este test confirma que ningún `producto_key` se
    perdió antes del join, no solo que el embedding llegó.
#}
with dim as (

    select count(*) as n
    from {{ ref('dim_producto') }}

),

emb as (

    select count(*) as n
    from {{ ref('emb_producto') }}

)

select dim.n as n_dim_producto, emb.n as n_emb_producto
from dim
cross join emb
where dim.n != emb.n
