{#
    Falla si la serie de `dim_fecha` tiene huecos: el número de filas tiene
    que ser exactamente `date_diff(max, min, day) + 1`. `unique` en
    `fecha_key` ya descarta duplicados, así que esto es la otra mitad: que
    no falte ningún día del rango.
#}
with medidas as (

    select
        count(*) as filas,
        date_diff(max(fecha_key), min(fecha_key), day) + 1 as dias_esperados
    from {{ ref('dim_fecha') }}

)
select *
from medidas
where filas != dias_esperados
