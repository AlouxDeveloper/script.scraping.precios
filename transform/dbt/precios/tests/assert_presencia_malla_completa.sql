{#
    La malla de `mart_presencia_mes` está completa: filas = presentaciones
    del cliente observadas × cadenas de `dim_tienda` × meses publicados. Un
    hueco haría que Looker calcule el % de presencia sin esa cadena o ese
    mes. Devuelve una fila si el conteo no cuadra.
#}

with esperado as (

    select
        (
            select count(distinct ndf_id)
            from {{ ref('mart_precio_cadena_mes') }}
            where es_cliente
        )
        * (select count(*) from {{ ref('dim_tienda') }})
        * (select count(distinct mes) from {{ ref('mart_precio_cadena_mes') }})
            as filas_esperadas

)

select
    esperado.filas_esperadas,
    (select count(*) from {{ ref('mart_presencia_mes') }}) as filas_reales
from esperado
where
    esperado.filas_esperadas
    != (select count(*) from {{ ref('mart_presencia_mes') }})
