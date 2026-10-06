{#
    Presencia de cada presentación del cliente por cadena y mes (M10,
    ALD-102). Grano `(ndf_id, tienda_key, mes)` en malla completa:
    presentaciones del cliente observadas al menos una vez en el panel × las
    19 cadenas × los meses publicados de `mart_precio_cadena_mes`.

    Estado:
    - `Cadena sin captura`: la cadena no tiene ningún precio ese mes en
      `fact_precios`, de ningún producto. No es ausencia del producto sino
      falta de dato, y no entra al denominador.
    - `Detectado`: la presentación tiene precio en la cadena ese mes,
      atípico o no (un vendedor externo también es presencia).
    - `No detectado`: la cadena se capturó y la presentación no apareció.
      Es cota inferior: incluye los listings que el cruce no asignó
      (recall Sanfer ~69% del techo, PRD §11).

    El % de presencia no se precalcula: Looker suma `detectado_n` entre
    `capturada_n` para que responda a los filtros de cadena, mes y
    producto. Solo entran presentaciones observadas; la cobertura del
    portafolio completo es del informe interno.
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

with precios_cliente as (

    select *
    from {{ ref('mart_precio_cadena_mes') }}
    where es_cliente

),

productos as (

    select
        ndf_id,
        any_value(marca) as marca,
        any_value(presentacion) as presentacion,
        any_value(molecula) as molecula,
        any_value(via) as via,
        any_value(forma) as forma,
        any_value(genero) as genero
    from precios_cliente
    group by ndf_id

),

meses as (

    select distinct mes
    from {{ ref('mart_precio_cadena_mes') }}

),

capturadas as (

    select distinct
        tienda_key,
        date_trunc(fecha_key, month) as mes
    from {{ ref('fact_precios') }}

)

select
    productos.ndf_id,
    dim_tienda.tienda_key,
    meses.mes,
    dim_tienda.tienda_nombre as cadena,
    case
        when capturadas.tienda_key is null then 'Cadena sin captura'
        when precios_cliente.ndf_id is not null then 'Detectado'
        else 'No detectado'
    end as estado,
    if(precios_cliente.ndf_id is not null, 1, 0) as detectado_n,
    if(capturadas.tienda_key is not null, 1, 0) as capturada_n,
    productos.marca,
    productos.presentacion,
    productos.molecula,
    productos.via,
    productos.forma,
    productos.genero
from productos
cross join {{ ref('dim_tienda') }} as dim_tienda
cross join meses
left join capturadas
    on dim_tienda.tienda_key = capturadas.tienda_key
    and meses.mes = capturadas.mes
left join precios_cliente
    on productos.ndf_id = precios_cliente.ndf_id
    and dim_tienda.tienda_key = precios_cliente.tienda_key
    and meses.mes = precios_cliente.mes
