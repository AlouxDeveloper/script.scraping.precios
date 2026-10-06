{#
    Estadísticos por presentación NDF y mes (M2, M3 y M7, ALD-101). Grano
    `(ndf_id, mes)`, sobre las cadenas de `mart_precio_cadena_mes` sin
    atípicos: un precio por cadena, así que n es número de cadenas.

    M2 y M3 exigen 4 o más cadenas (mínimo OMS/HAI) y quedan nulos por
    debajo, incluidos el mínimo, el máximo y sus cadenas: con 2 o 3 precios
    un "rango" no describe al mercado. `precio_tipico` es la mediana con
    cualquier n; la usa V4 porque los genéricos suelen estar en 1 o 2
    cadenas, y el dashboard la muestra siempre junto a `cadenas_n`.

    Cuantiles con `PERCENTILE_CONT`, que interpola igual que el tipo 7 de
    Hyndman y Fan (el default de R y numpy). Es función analítica en
    BigQuery: se calcula por ventana y se colapsa con `any_value`.

    M7: `precio_mg` = `precio_tipico` / `mg_por_envase`. Solo es comparable
    dentro del mismo `grupo_competitivo` (misma molécula y vía, la DDD es
    constante); por eso el grupo viaja en la misma fila.
#}
{{
    config(
        partition_by={
            'field': 'mes',
            'data_type': 'date',
            'granularity': 'month'
        },
        cluster_by=['ndf_id']
    )
}}

with precios as (

    select
        *,
        if(es_atipico, null, precio) as precio_valido,
        if(es_atipico, null, cadena) as cadena_valida
    from {{ ref('mart_precio_cadena_mes') }}

),

-- PERCENTILE_CONT ignora los NULL: anular el precio de los atípicos los
-- saca de los cuantiles sin perderlos del conteo `atipicos_n`. El
-- percentil va como NUMERIC: con un literal FLOAT64 BigQuery convierte
-- también el precio y los cuantiles dejan de ser exactos.
cuantiles as (

    select
        *,
        percentile_cont(precio_valido, numeric '0.25') over mercado as p25,
        percentile_cont(precio_valido, numeric '0.5') over mercado as p50,
        percentile_cont(precio_valido, numeric '0.75') over mercado as p75
    from precios
    window mercado as (partition by ndf_id, mes)

),

agregado as (

    select
        ndf_id,
        mes,
        countif(not es_atipico) as cadenas_n,
        countif(es_atipico) as atipicos_n,
        min(precio_valido) as precio_min,
        any_value(p25) as precio_p25,
        any_value(p50) as precio_mediana,
        any_value(p75) as precio_p75,
        max(precio_valido) as precio_max,
        -- El nombre de la cadena desempata para que la elección sea
        -- determinística cuando dos cadenas comparten el extremo.
        array_agg(
            cadena_valida ignore nulls order by precio_valido, cadena_valida limit 1
        )[safe_offset(0)] as cadena_min,
        array_agg(
            cadena_valida ignore nulls
            order by precio_valido desc, cadena_valida limit 1
        )[safe_offset(0)] as cadena_max,
        any_value(marca) as marca,
        any_value(presentacion) as presentacion,
        any_value(laboratorio) as laboratorio,
        any_value(molecula) as molecula,
        any_value(via) as via,
        any_value(forma) as forma,
        any_value(genero) as genero,
        any_value(es_cliente) as es_cliente
    from cuantiles
    group by ndf_id, mes

)

select
    agregado.ndf_id,
    agregado.mes,
    agregado.cadenas_n,
    agregado.atipicos_n,

    -- M2
    if(agregado.cadenas_n >= 4, agregado.precio_min, null) as precio_min,
    if(agregado.cadenas_n >= 4, agregado.precio_p25, null) as precio_p25,
    if(agregado.cadenas_n >= 4, agregado.precio_mediana, null)
        as precio_mediana,
    if(agregado.cadenas_n >= 4, agregado.precio_p75, null) as precio_p75,
    if(agregado.cadenas_n >= 4, agregado.precio_max, null) as precio_max,
    if(agregado.cadenas_n >= 4, agregado.cadena_min, null) as cadena_min,
    if(agregado.cadenas_n >= 4, agregado.cadena_max, null) as cadena_max,

    -- M3
    if(
        agregado.cadenas_n >= 4,
        round(agregado.precio_max / agregado.precio_min - 1, 4),
        null
    ) as rango_rel_pct,
    if(
        agregado.cadenas_n >= 4,
        round(
            (agregado.precio_p75 - agregado.precio_p25)
            / agregado.precio_mediana,
            4
        ),
        null
    ) as iqr_rel_pct,

    agregado.precio_mediana as precio_tipico,

    -- M7
    int_ndf_grupo_competitivo.mg_por_envase,
    -- `safe_divide`: una presentación que el catálogo escribe con 0
    -- piezas daría división entre cero.
    safe_divide(
        agregado.precio_mediana, int_ndf_grupo_competitivo.mg_por_envase
    ) as precio_mg,
    int_ndf_grupo_competitivo.grupo_competitivo,

    agregado.marca,
    agregado.presentacion,
    agregado.laboratorio,
    agregado.molecula,
    agregado.via,
    agregado.forma,
    agregado.genero,
    agregado.es_cliente
from agregado
inner join {{ ref('int_ndf_grupo_competitivo') }} as int_ndf_grupo_competitivo
    using (ndf_id)
-- Una presentación cuyas cadenas son todas atípicas no tiene precio típico.
where agregado.cadenas_n > 0
