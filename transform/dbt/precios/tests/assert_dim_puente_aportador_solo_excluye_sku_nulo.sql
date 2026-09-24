{#
    Falla si `dim_puente_aportador` pierde filas por algo que no sea lo
    documentado: el centinela `sku` NULL (6 filas) y los duplicados
    literales que repiten exactamente `(tienda_key, sku, ndf_id)` (2,196
    pares). El join contra `dim_tienda` no debería perder nada -todo
    `aportador_clave` del crosswalk tiene su fila en el seed, incluidos
    `fesa`/`yza`-, así que cualquier diferencia extra sería una pérdida
    silenciosa del join o del dedup.
#}
with resuelto as (

    select distinct
        dim_tienda.tienda_key,
        stg_puente_aportador.sku,
        stg_puente_aportador.ndf_id
    from {{ ref('stg_puente_aportador') }} as stg_puente_aportador
    inner join {{ ref('dim_tienda') }} as dim_tienda
        on stg_puente_aportador.aportador_clave = dim_tienda.aportador_clave
    where stg_puente_aportador.sku is not null

),

conteos as (

    select
        (select count(*) from {{ ref('dim_puente_aportador') }}) as n_dim,
        (select count(*) from resuelto) as n_triples_esperados

)

select *
from conteos
where n_dim != n_triples_esperados
