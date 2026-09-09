{#
    Falla si los NULL de `fecha_lanzamiento` en stg_ndf no cuadran con el
    conteo del centinela `190012` en el origen: garantiza que el tipado no
    perdió ni inventó fechas, solo neutralizó el centinela.
#}
with conteos as (

    select
        (
            select count(*)
            from {{ ref('stg_ndf') }}
            where fecha_lanzamiento is null
        ) as nulos_stg,
        (
            select count(*)
            from {{ source('bronce', 'ndf_ext') }}
            where fecha_lanzamiento = '190012'
        ) as centinela_origen

)

select *
from conteos
where nulos_stg != centinela_origen
