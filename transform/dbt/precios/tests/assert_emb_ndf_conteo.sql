{#
    Falla si `emb_ndf` no cubre exactamente el mismo universo que
    `dim_ndf` (ver ALD-70). Gemelo de `assert_emb_producto_conteo.sql`.
#}
with dim as (

    select count(*) as n
    from {{ ref('dim_ndf') }}

),

emb as (

    select count(*) as n
    from {{ ref('emb_ndf') }}

)

select dim.n as n_dim_ndf, emb.n as n_emb_ndf
from dim
cross join emb
where dim.n != emb.n
