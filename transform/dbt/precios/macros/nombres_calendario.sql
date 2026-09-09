{#
    Nombres de calendario en español para la capa gold.

    `FORMAT_DATE('%B', ...)` y `FORMAT_DATE('%A', ...)` de BigQuery
    devuelven el nombre en inglés y no respetan la locale de la sesión, así
    que el mapeo de número a nombre es un `CASE` explícito.

    Vive en una macro y no inline porque `dim_fecha` lo usa dos veces y es
    justo lo que el principio DRY del proyecto pide abstraer: la lógica que
    se repite va a `macros/`.
#}

{% macro nombre_mes(fecha) %}
    case extract(month from {{ fecha }})
        when 1 then 'enero'
        when 2 then 'febrero'
        when 3 then 'marzo'
        when 4 then 'abril'
        when 5 then 'mayo'
        when 6 then 'junio'
        when 7 then 'julio'
        when 8 then 'agosto'
        when 9 then 'septiembre'
        when 10 then 'octubre'
        when 11 then 'noviembre'
        when 12 then 'diciembre'
    end
{% endmacro %}

{% macro nombre_dia_semana(fecha) %}
    {#-
        `EXTRACT(DAYOFWEEK FROM ...)` en BigQuery numera 1=domingo .. 7=sábado.
    -#}
    case extract(dayofweek from {{ fecha }})
        when 1 then 'domingo'
        when 2 then 'lunes'
        when 3 then 'martes'
        when 4 then 'miércoles'
        when 5 then 'jueves'
        when 6 then 'viernes'
        when 7 then 'sábado'
    end
{% endmacro %}
