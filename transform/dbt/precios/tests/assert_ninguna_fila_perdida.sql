{#
    Falla si precios + precios_cuarentena no reconstruye exactamente
    precios_ext: el equivalente en silver de la ErrorReconciliacion que
    load/ ya hace contra raw (load/src/precios_load/bronce.py:163-168),
    y solo es posible porque existe la cuarentena.
#}
with conteos as (

    select
        (select count(*) from {{ ref('precios') }}) as n_precios,
        (select count(*) from {{ ref('precios_cuarentena') }}) as n_cuarentena,
        (select count(*) from {{ source('bronce', 'precios_ext') }}) as n_bronce

)

select *
from conteos
where n_precios + n_cuarentena != n_bronce
