{#
    Productos en la banda gris del entity resolution vectorial, con su
    top-10 de candidatos NDF: la entrada del método 3 (verificación por
    LLM). Grano `(producto_key, rank_candidato)`, un candidato por fila.

    Entra un producto cuando `int_match_ndf` lo deja en `cuarentena` (la
    marca del NDF aparece en la descripción y la distancia está dentro del
    tau, pero falla el margen, la guarda de magnitudes o su tienda/división
    está en `cuarentena_forzada`) y además ningún método por código le
    asignó `ndf_id`: la cuarentena de un producto que ya tiene crosswalk no
    es trabajo pendiente. `motivo` dice cuál de las tres falló, en ese
    orden de prioridad.

    Se guardan los 10 candidatos y no solo el rank 1 porque el método 3
    elige entre ellos (o ninguno): una cuarentena por margen es justo el
    caso en que el segundo puede ser el correcto. La descripción de la
    tienda y la marca/presentación del catálogo van lado a lado para que
    quien revise no tenga que hacer joins.

    Vive en silver, no en `precios_ml`: es un insumo de trabajo que se
    consume fuera del entity resolution vectorial, no un artefacto de
    calibración.
#}
{{
    config(
        materialized='table',
        cluster_by=['producto_key']
    )
}}

with en_cuarentena as (

    select
        int_match_ndf.producto_key,
        int_producto.tienda_key,
        int_producto.descripcion,
        case
            when int_match_ndf.margen is null
                or int_match_ndf.margen < {{ var('delta_min') }}
                then 'margen'
            when not int_match_ndf.guarda_ok then 'guarda'
            else 'estrato_forzado'
        end as motivo
    from {{ ref('int_match_ndf') }} as int_match_ndf
    inner join {{ ref('int_producto') }} as int_producto
        on int_producto.producto_key = int_match_ndf.producto_key
    where int_match_ndf.decision = 'cuarentena'
        and int_producto.ndf_id is null

)

select
    en_cuarentena.producto_key,
    en_cuarentena.tienda_key,
    en_cuarentena.motivo,
    candidatos.rank_desde_producto as rank_candidato,
    en_cuarentena.descripcion,
    candidatos.ndf_id,
    dim_ndf.producto as ndf_producto,
    dim_ndf.presentacion as ndf_presentacion,
    dim_ndf.division as ndf_division,
    candidatos.distancia
from en_cuarentena
inner join {{ ref('int_candidatos_producto') }} as candidatos
    on candidatos.producto_key = en_cuarentena.producto_key
inner join {{ ref('dim_ndf') }} as dim_ndf
    on dim_ndf.ndf_id = candidatos.ndf_id
