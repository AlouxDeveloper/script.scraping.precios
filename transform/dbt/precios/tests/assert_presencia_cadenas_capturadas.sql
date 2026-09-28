{#
    Las cadenas capturadas por mes de `mart_presencia_mes` cuadran con
    `fact_precios`: el denominador del % de presencia es exactamente el
    conjunto de cadenas con algún precio ese mes. Devuelve los meses
    publicados donde el conteo difiere.
#}

with en_presencia as (

    select mes, count(distinct tienda_key) as cadenas_n
    from {{ ref('mart_presencia_mes') }}
    where capturada_n = 1
    group by mes

),

en_fact as (

    select date_trunc(fecha_key, month) as mes, count(distinct tienda_key) as cadenas_n
    from {{ ref('fact_precios') }}
    group by mes

)

select
    en_presencia.mes,
    en_presencia.cadenas_n as cadenas_presencia,
    en_fact.cadenas_n as cadenas_fact
from en_presencia
left join en_fact using (mes)
where en_presencia.cadenas_n is distinct from en_fact.cadenas_n
