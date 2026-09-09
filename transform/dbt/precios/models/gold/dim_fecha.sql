{#
    Dimensión de fecha (Kimball): una fila por día natural entre la primera
    y la última `fecha_captura` observada en `precios`.

    El rango sale del dato, no de literales. El histórico crece cada mes y
    una fecha de fin hardcodeada se queda corta sin avisar; `date_spine`
    entre el `min` y el `max` reales cubre siempre exactamente lo que hay.

    Los límites van como subconsulta escalar directa contra `precios` -no
    como CTE- porque `dbt_utils.date_spine` compila su propio bloque `with`
    y una CTE de este modelo no sería visible dentro. Son dos agregados
    `min`/`max` sobre una columna DATE: barato para una dimensión que se
    reconstruye de vez en cuando.

    Desviación deliberada del page de Notion: el nombre del mes es
    `mes_nombre` y el DATE que empata con silver es `mes_inicio`. `mes` a
    secas ya es el DATE de partición en `precios` y `precios_cuarentena`;
    reusar ese nombre para una cadena distinta en la misma base de datos es
    una trampa que tarde o temprano cuesta un join mal hecho.
#}

with serie as (

    {#- `date_spine` trata `end_date` como exclusivo: +1 día para que el
        último día observado entre en la serie. -#}
    {{
        dbt_utils.date_spine(
            datepart="day",
            start_date="(select date(min(fecha_captura)) from " ~ ref('precios') ~ ")",
            end_date="(select date_add(date(max(fecha_captura)), interval 1 day) from " ~ ref('precios') ~ ")"
        )
    }}

),

calendario as (

    select cast(date_day as date) as fecha_key
    from serie

)

select
    fecha_key,
    extract(year from fecha_key) as anio,
    extract(quarter from fecha_key) as trimestre,
    extract(month from fecha_key) as mes_num,
    {{ nombre_mes('fecha_key') }} as mes_nombre,
    date_trunc(fecha_key, month) as mes_inicio,
    extract(isoweek from fecha_key) as semana_iso,
    extract(day from fecha_key) as dia,
    -- lunes=1 .. domingo=7 (ISO), consistente con `semana_iso`.
    mod(extract(dayofweek from fecha_key) + 5, 7) + 1 as dia_semana_num,
    {{ nombre_dia_semana('fecha_key') }} as dia_semana_nombre
from calendario
