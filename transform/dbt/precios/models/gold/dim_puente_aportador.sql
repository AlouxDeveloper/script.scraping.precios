{#
    Crosswalk tienda-sku-ndf (Kimball: dimensión-puente). Insumo del entity
    resolution: `dim_producto.ndf_id`/`match_method='aportadores'` consume
    esta tabla (solo candidatos únicos y con `ndf_id` real, ver
    `dim_producto.sql`), pero esta tabla en sí no decide nada — solo deja el
    crosswalk limpio con `tienda_key` resuelto. `sku` NO coincide con
    `dim_producto.sku` para la mayoría de las tiendas (match 0-35% según
    tienda, ver `stg_puente_aportador`): por eso solo resuelve ~25% de
    `dim_producto`, no más. El resto sigue pendiente de una pasada por texto.

    Grano `(tienda_key, sku, ndf_id)`, NO `(tienda_key, sku)`: 71 combos de
    `(tienda_key, sku)` en el corte 260910 traen más de un `ndf_id`
    candidato — ambigüedad real del aportador, no un bug del join. Resolver
    cuál es el correcto es trabajo del entity resolution (embeddings contra
    `dim_ndf`), no de este modelo.

    `stg_puente_aportador` inner join `dim_tienda` por `aportador_clave`:
    las 2 tiendas del crosswalk sin scraping (`farmacon`, `farmesp`) ya
    están en el seed, así que ese join no pierde filas. Se filtran las filas
    con `sku` NULL (el centinela `correlativo = '000000000000000'`, 5 filas)
    y se dedupean 642 pares de filas que repetían exactamente el mismo
    `(tienda_key, sku, ndf_id)` -duplicados literales de origen, no
    candidatos distintos- con `row_number()`; `producto`/`descripcion` no
    entran al desempate porque son solo contexto de auditoría, no identidad.
    El test `assert_dim_puente_aportador_solo_excluye_sku_nulo` confirma que
    la diferencia contra `stg_puente_aportador` es exactamente sku NULL más
    esos duplicados literales, no una pérdida silenciosa del join.

    `producto`/`descripcion` viajan para dar contexto de auditoría (comparar
    a ojo contra `dim_producto`/`dim_ndf`), no para exhibirse en BI.
#}
{{
    config(
        materialized='table',
        cluster_by=['tienda_key']
    )
}}

with resuelto as (

    select
        dim_tienda.tienda_key,
        stg_puente_aportador.sku,
        stg_puente_aportador.ndf_id,
        stg_puente_aportador.producto,
        stg_puente_aportador.descripcion,
        row_number() over (
            partition by
                dim_tienda.tienda_key,
                stg_puente_aportador.sku,
                stg_puente_aportador.ndf_id
            order by
                stg_puente_aportador.producto asc,
                stg_puente_aportador.descripcion asc
        ) as rn
    from {{ ref('stg_puente_aportador') }} as stg_puente_aportador
    inner join {{ ref('dim_tienda') }} as dim_tienda
        on stg_puente_aportador.aportador_clave = dim_tienda.aportador_clave
    where stg_puente_aportador.sku is not null

)

select
    tienda_key,
    sku,
    ndf_id,
    producto,
    descripcion
from resuelto
where rn = 1
