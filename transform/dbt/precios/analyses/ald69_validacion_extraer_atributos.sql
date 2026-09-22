{#
    Validación de macros/extraer_atributos.sql (ALD-69) contra los pares
    verdaderos del crosswalk de aportadores -no es un modelo ni un test, es
    la medición que decide si la guarda de presentación se aplica tal cual,
    se afloja con tolerancia, o se restringe a ciertas unidades. Se compila
    con `dbt compile` y se corre el SQL resultante a mano; no se materializa.
#}

with pares as (

    select
        p.producto_key,
        p.tienda_key,
        -- dim_producto.descripcion ya pasó por limpiar_texto (stg_precios);
        -- dim_ndf.descripcion no -stg_ndf la deja tal cual llega del Excel,
        -- con "/" y "." sueltos. Se limpia aqui para comparar manzanas con
        -- manzanas: sin esto, un combo "400/100MG" del catalogo no
        -- tokeniza igual que su equivalente ya limpio del lado tienda.
        {{ extraer_atributos('p.descripcion') }} as lado_tienda,
        {{ extraer_atributos(limpiar_texto('n.descripcion')) }} as lado_catalogo
    from {{ ref('dim_producto') }} as p
    inner join {{ ref('dim_ndf') }} as n
        on n.ndf_id = p.ndf_id
    where p.match_method = 'aportadores'

),

comparado as (

    select
        producto_key,
        tienda_key,
        -- concordante: ambos declaran y coinciden. discordante: ambos
        -- declaran y difieren -el falso negativo real de la guarda. de un
        -- lado: no hay caso para comparar, la guarda no penaliza.
        case
            when lado_tienda.dosis_mg is null or lado_catalogo.dosis_mg is null
                then 'de_un_lado'
            when lado_tienda.dosis_mg = lado_catalogo.dosis_mg then 'concordante'
            else 'discordante'
        end as dosis_mg_resultado,
        case
            when lado_tienda.volumen_ml is null or lado_catalogo.volumen_ml is null
                then 'de_un_lado'
            when lado_tienda.volumen_ml = lado_catalogo.volumen_ml then 'concordante'
            else 'discordante'
        end as volumen_ml_resultado,
        case
            when lado_tienda.masa_g is null or lado_catalogo.masa_g is null
                then 'de_un_lado'
            when lado_tienda.masa_g = lado_catalogo.masa_g then 'concordante'
            else 'discordante'
        end as masa_g_resultado,
        case
            when lado_tienda.piezas is null or lado_catalogo.piezas is null
                then 'de_un_lado'
            when lado_tienda.piezas = lado_catalogo.piezas then 'concordante'
            else 'discordante'
        end as piezas_resultado
    from pares

)

select
    'dosis_mg' as atributo, dosis_mg_resultado as resultado, count(*) as n_filas
from comparado
group by dosis_mg_resultado
union all
select 'volumen_ml', volumen_ml_resultado, count(*)
from comparado
group by volumen_ml_resultado
union all
select 'masa_g', masa_g_resultado, count(*)
from comparado
group by masa_g_resultado
union all
select 'piezas', piezas_resultado, count(*)
from comparado
group by piezas_resultado
order by atributo, resultado
