{#
    Competencia de cada presentación del cliente (M8 y M9, ALD-101). Grano
    `(ndf_id, ndf_id_competidor, mes)`: una fila por cada presentación del
    mismo grupo competitivo con precio ese mes, incluida la propia, más una
    fila sintética "Genéricos (mediana)" con `ndf_id_competidor` NULL. Es la
    tabla de la vista V4.

    La escala es `precio_mg` (M7), comparable solo dentro del grupo (misma
    molécula exacta, vía y mg por unidad).

    M8: percentil de rango medio, 100 · (#más baratos + ½ · #empatados) / N,
    con la propia presentación dentro de N y de los empatados. Exige N >= 5;
    por debajo, el dashboard muestra la lista de competidores. Se calcula
    para cada fila, no solo para la del cliente: la de la propia
    presentación es la cifra del informe y las demás ubican a cada
    competidor en la misma escala.

    M9: prima contra la mediana del `precio_mg` de los genéricos (género
    `G.P.` del NDF) del grupo; exige 3 o más. Las marcas propias de las
    cadenas pueden venir en otro género y entonces no cuentan como genérico.

    Los atributos sin sufijo (`marca`, `presentacion`, `molecula`, `via`,
    `forma`, `genero`) son de la presentación del cliente y los del
    competidor llevan `_competidor`: Looker filtra por nombre de campo entre
    tablas, y un filtro global de "Presentación" o "Molécula" tiene que
    elegir al producto del cliente, no a sus rivales.

    `en_grafica` acota la gráfica de V4 a los 10 más baratos, los 10 más
    caros, la propia presentación y la fila de genéricos: un grupo como
    ibuprofeno 400 mg tiene decenas de presentaciones.
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

with con_precio as (

    select
        ndf_id,
        mes,
        grupo_competitivo,
        precio_mg,
        precio_tipico,
        cadenas_n,
        marca,
        presentacion,
        laboratorio,
        molecula,
        via,
        forma,
        genero,
        genero = 'G.P.' as es_generico,
        es_cliente
    from {{ ref('mart_precio_ndf_mes') }}
    where grupo_competitivo is not null and precio_mg is not null

),

catalogo as (

    select grupo_competitivo, count(*) as catalogo_n
    from {{ ref('int_ndf_grupo_competitivo') }}
    where grupo_competitivo is not null
    group by grupo_competitivo

),

en_grupo as (

    select
        *,
        count(*) over grupo as presentaciones_n,
        rank() over (grupo order by precio_mg) - 1 as mas_baratas_n,
        rank() over (grupo order by precio_mg desc) - 1 as mas_caras_n,
        countif(es_generico) over grupo as genericos_n,
        percentile_cont(if(es_generico, precio_mg, null), numeric '0.5')
            over grupo as mediana_mg_genericos,
        percentile_cont(if(es_generico, precio_tipico, null), numeric '0.5')
            over grupo as mediana_tipico_genericos
    from con_precio
    window grupo as (partition by grupo_competitivo, mes)

),

competidores as (

    select
        cliente.ndf_id,
        cliente.mes,
        cliente.marca,
        cliente.presentacion,
        cliente.molecula,
        cliente.via,
        cliente.forma,
        cliente.genero,
        competidor.ndf_id as ndf_id_competidor,
        competidor.marca as marca_competidor,
        competidor.presentacion as presentacion_competidor,
        competidor.laboratorio as laboratorio_competidor,
        competidor.ndf_id = cliente.ndf_id as es_propio,
        competidor.es_generico,
        false as es_sintetica,
        competidor.precio_mg,
        competidor.precio_tipico,
        competidor.cadenas_n,
        if(
            competidor.presentaciones_n >= 5,
            round(
                -- Empatadas = N − más baratas − más caras, incluida la
                -- propia.
                100 * (
                    competidor.mas_baratas_n
                    + 0.5 * (
                        competidor.presentaciones_n
                        - competidor.mas_baratas_n
                        - competidor.mas_caras_n
                    )
                ) / competidor.presentaciones_n,
                1
            ),
            null
        ) as percentil,
        if(
            competidor.genericos_n >= 3,
            round(competidor.precio_mg / competidor.mediana_mg_genericos, 2),
            null
        ) as prima_genericos,
        competidor.presentaciones_n,
        competidor.genericos_n,
        competidor.grupo_competitivo,
        row_number() over (
            partition by cliente.ndf_id, cliente.mes
            order by competidor.precio_mg, competidor.ndf_id
        ) as posicion_barata,
        row_number() over (
            partition by cliente.ndf_id, cliente.mes
            order by competidor.precio_mg desc, competidor.ndf_id
        ) as posicion_cara
    from en_grupo as cliente
    inner join en_grupo as competidor
        on cliente.grupo_competitivo = competidor.grupo_competitivo
        and cliente.mes = competidor.mes
    where cliente.es_cliente

),

genericos as (

    select
        ndf_id,
        mes,
        marca,
        presentacion,
        molecula,
        via,
        forma,
        genero,
        cast(null as string) as ndf_id_competidor,
        'Genéricos (mediana)' as marca_competidor,
        cast(null as string) as presentacion_competidor,
        cast(null as string) as laboratorio_competidor,
        false as es_propio,
        true as es_generico,
        true as es_sintetica,
        mediana_mg_genericos as precio_mg,
        mediana_tipico_genericos as precio_tipico,
        cast(null as int64) as cadenas_n,
        cast(null as float64) as percentil,
        -- La referencia de la prima es la propia mediana: 1 por definición.
        cast(1 as numeric) as prima_genericos,
        presentaciones_n,
        genericos_n,
        grupo_competitivo,
        true as en_grafica
    from en_grupo
    where es_cliente and genericos_n >= 3

)

select
    competidores.* except (posicion_barata, posicion_cara),
    competidores.posicion_barata <= 10
    or competidores.posicion_cara <= 10
    or competidores.es_propio as en_grafica,
    catalogo.catalogo_n
from competidores
inner join catalogo using (grupo_competitivo)

union all

select
    genericos.*,
    catalogo.catalogo_n
from genericos
inner join catalogo using (grupo_competitivo)
