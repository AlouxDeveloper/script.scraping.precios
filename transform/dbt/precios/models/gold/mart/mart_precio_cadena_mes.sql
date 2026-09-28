{#
    Panel mensual por cadena del dashboard (PRD §12, ALD-100). Grano
    `(ndf_id, tienda_key, mes)`: un precio por presentación NDF, cadena y
    mes, para todo el mercado (todos los laboratorios con `ndf_id`, no solo
    el cliente). Alimenta M1, M4, M11, M12 y M13, y es la base de los demás
    `mart_`.

    Meses publicados: desde `mes_inicio_panel`, con al menos
    `min_cadenas_mes` cadenas capturadas en `fact_precios` (deja fuera nov
    2025, con una sola tienda) y nunca el mes en curso, que todavía no tiene
    su captura completa. El mes en curso sale de `dbt.current_timestamp()` y
    no de `current_date()` para que el unit test pueda fijar "hoy".

    Colapso: una cadena puede tener varios listings de la misma presentación
    y varias capturas en el mes. Gana el precio efectivo más bajo, y el
    regular y la oferta se toman de ese mismo listing y día: mezclar el
    regular de uno con la oferta de otro inventaría un descuento que nadie
    publicó.

    Atípicos (M13): z modificado de Iglewicz y Hoaglin sobre ln(precio),
    entre cadenas de la misma presentación y mes. Con menos de 4 cadenas no
    se evalúa: la MAD de 2 o 3 puntos no distingue un atípico de la
    dispersión normal. Si la MAD vale 0 (más de la mitad de las cadenas con
    el mismo precio) se usa 1.2533·MeanAD, la alternativa de los mismos
    autores; si también vale 0, todos los precios son iguales y z = 0.

    Posición (M4): contra la mediana de las cadenas no atípicas, solo si
    quedan 4 o más (mínimo OMS/HAI). La mediana usa todo el mercado a
    propósito: el filtro "Cadena" de Looker no la recalcula.
#}
{{
    config(
        partition_by={
            'field': 'mes',
            'data_type': 'date',
            'granularity': 'month'
        },
        cluster_by=['ndf_id', 'tienda_key']
    )
}}

with meses_publicados as (

    select date_trunc(fecha_key, month) as mes
    from {{ ref('fact_precios') }}
    group by mes
    having
        count(distinct tienda_key) >= {{ var('min_cadenas_mes') }}
        and mes >= date '{{ var("mes_inicio_panel") }}'
        and mes < date_trunc(
            date({{ dbt.current_timestamp() }}, 'America/Mexico_City'), month
        )

),

precios as (

    select
        dim_producto.ndf_id,
        fact_precios.tienda_key,
        date_trunc(fact_precios.fecha_key, month) as mes,
        fact_precios.producto_key,
        fact_precios.fecha_key,
        fact_precios.precio_lista,
        fact_precios.precio_oferta,
        coalesce(fact_precios.precio_oferta, fact_precios.precio_lista)
            as precio,
        dim_producto.match_method,
        dim_producto.url_imagen_actual
    from {{ ref('fact_precios') }} as fact_precios
    inner join {{ ref('dim_producto') }} as dim_producto
        on fact_precios.producto_key = dim_producto.producto_key
    where dim_producto.ndf_id is not null

),

-- Desempate después del precio efectivo: el regular más bajo (el descuento
-- menos inflado), la captura más reciente y `producto_key` para que la
-- elección sea determinística entre builds.
colapsado as (

    select
        precios.ndf_id,
        precios.tienda_key,
        precios.mes,
        count(distinct precios.producto_key) as listings_n,
        array_agg(
            struct(
                precios.precio,
                precios.precio_lista,
                precios.precio_oferta,
                precios.match_method,
                precios.url_imagen_actual
            )
            order by
                precios.precio,
                precios.precio_lista,
                precios.fecha_key desc,
                precios.producto_key
            limit 1
        )[offset(0)] as elegido
    from precios
    inner join meses_publicados using (mes)
    group by precios.ndf_id, precios.tienda_key, precios.mes

),

con_mediana_ln as (

    select
        ndf_id,
        tienda_key,
        mes,
        listings_n,
        elegido.precio,
        elegido.precio_lista as precio_regular,
        elegido.precio_oferta,
        elegido.match_method,
        elegido.url_imagen_actual as url_imagen,
        ln(cast(elegido.precio as float64)) as ln_precio,
        count(*) over mercado as cadenas_n,
        percentile_cont(ln(cast(elegido.precio as float64)), 0.5)
            over mercado as mediana_ln
    from colapsado
    window mercado as (partition by ndf_id, mes)

),

con_dispersion as (

    select
        *,
        percentile_cont(abs(ln_precio - mediana_ln), 0.5)
            over mercado as mad,
        avg(abs(ln_precio - mediana_ln)) over mercado as mean_ad
    from con_mediana_ln
    window mercado as (partition by ndf_id, mes)

),

con_atipicos as (

    select
        *,
        case
            when cadenas_n < 4 then null
            when mad > 0 then 0.6745 * (ln_precio - mediana_ln) / mad
            when mean_ad > 0
                then (ln_precio - mediana_ln) / (1.2533 * mean_ad)
            else 0
        end as z_robusto
    from con_dispersion

),

-- PERCENTILE_CONT ignora los NULL, así que la mediana sin atípicos sale de
-- anular el precio de los atípicos en vez de filtrar filas: los atípicos se
-- quedan en la tabla con su posición contra el mercado.
con_mercado as (

    select
        *,
        coalesce(abs(z_robusto) > 3.5, false) as es_atipico,
        countif(coalesce(abs(z_robusto) <= 3.5, true)) over mercado
            as cadenas_sin_atipicos_n,
        percentile_cont(
            if(coalesce(abs(z_robusto) <= 3.5, true), precio, null), 0.5
        ) over mercado as mediana_sin_atipicos
    from con_atipicos
    window mercado as (partition by ndf_id, mes)

),

con_posicion as (

    select
        *,
        if(cadenas_sin_atipicos_n >= 4, mediana_sin_atipicos, null)
            as mediana_mercado,
        precio / if(cadenas_sin_atipicos_n >= 4, mediana_sin_atipicos, null)
            - 1 as pct_vs_mediana
    from con_mercado

)

select
    con_posicion.ndf_id,
    con_posicion.tienda_key,
    con_posicion.mes,
    dim_tienda.tienda_nombre as cadena,

    -- M1 y M11
    con_posicion.precio,
    con_posicion.precio_regular,
    con_posicion.precio_oferta,
    round(1 - con_posicion.precio_oferta / con_posicion.precio_regular, 4)
        as descuento_pct,
    con_posicion.listings_n,

    -- M13
    con_posicion.cadenas_n,
    round(con_posicion.z_robusto, 2) as z_robusto,
    con_posicion.es_atipico,

    -- M4. Los cortes ±5% y ±15% son convención de la industria (PRD M4) y
    -- se aplican sobre el valor sin redondear.
    con_posicion.mediana_mercado,
    round(con_posicion.pct_vs_mediana, 4) as pct_vs_mediana,
    case
        when con_posicion.pct_vs_mediana > 0.15 then 'Muy por encima'
        when con_posicion.pct_vs_mediana > 0.05 then 'Por encima'
        when con_posicion.pct_vs_mediana >= -0.05 then 'En paridad'
        when con_posicion.pct_vs_mediana >= -0.15 then 'Por debajo'
        when con_posicion.pct_vs_mediana < -0.15 then 'Muy por debajo'
    end as tramo,

    -- M12, solo para devs. Precisión medida de cada método: auditorías de
    -- ALD-58 (aportadores), del EAN cruzado y la calibración de ALD-95
    -- (vectorial, que depende de la división igual que su tau).
    con_posicion.match_method,
    case con_posicion.match_method
        when 'aportadores' then 0.990
        when 'ean_cruzado' then 0.994
        when 'vectorial' then if(dim_ndf.division = 'FARMA', 0.96, 0.85)
    end as precision_esperada,

    -- Atributos del NDF para los filtros de Looker.
    con_posicion.url_imagen,
    dim_ndf.producto as marca,
    dim_ndf.presentacion,
    dim_ndf.laboratorio,
    dim_ndf.molecula,
    -- La vía es la primera letra de la clave de forma farmacéutica (NFC).
    -- Se separa la vía oral sistémica (A-E) de la tópica bucal (K) para que
    -- una pastilla para la garganta no compita con una tableta.
    case left(dim_ndf.cve_ff, 1)
        when 'A' then 'ORAL'
        when 'B' then 'ORAL'
        when 'C' then 'ORAL'
        when 'D' then 'ORAL'
        when 'E' then 'ORAL'
        when 'F' then 'PARENTERAL'
        when 'G' then 'PARENTERAL'
        when 'H' then 'RECTAL'
        when 'I' then 'NASAL'
        when 'J' then 'OTRA'
        when 'K' then 'BUCAL'
        when 'M' then 'TOPICA'
        when 'N' then 'OFTALMICA'
        when 'P' then 'OTICA'
        when 'Q' then 'NASAL'
        when 'R' then 'INHALADA'
        when 'T' then 'VAGINAL'
    end as via,
    trim(dim_ndf.forma_farmaceutica_n3) as forma,
    dim_ndf.genero,
    dim_ndf.laboratorio = '{{ var("laboratorio_cliente") }}' as es_cliente
from con_posicion
inner join {{ ref('dim_tienda') }} as dim_tienda
    using (tienda_key)
inner join {{ ref('dim_ndf') }} as dim_ndf
    using (ndf_id)
