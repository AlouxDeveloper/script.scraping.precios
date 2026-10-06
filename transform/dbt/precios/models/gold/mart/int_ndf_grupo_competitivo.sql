{#
    Vía, magnitudes y grupo competitivo de cada presentación del catálogo NDF
    (M7-M9, ALD-101). Grano `ndf_id`, todo `dim_ndf`: el M8 dice cuántas
    presentaciones del grupo hay en catálogo, no solo cuántas tienen precio.
    Vive aparte para que los tres `mart_` lean la misma vía y el mismo grupo
    en vez de repetir el cálculo, y para auditar la extracción de mg sin
    pasar por los precios.

    Grupo competitivo: molécula exacta + vía + mg por unidad (PRD §11,
    2026-09-28). La molécula exacta separa las sales (naproxeno vs naproxeno
    sódico) y las combinaciones. La unidad de los mg se incluye en la llave
    para que 20 mg/ml de un jarabe no caiga con una tableta de 20 mg. Quedan
    sin grupo la molécula `SIN SAL` (productos de consumo) y la forma `SIN
    FF`.
#}
{{
    config(
        cluster_by=['grupo_competitivo']
    )
}}

with ndf as (

    select
        ndf_id,
        molecula,
        -- La vía es la primera letra de la clave de forma farmacéutica (NFC).
        -- La oral sistémica (A-E) va separada de la tópica bucal (K) para que
        -- una pastilla para la garganta no compita con una tableta. `S` es
        -- `SIN FF`; `V` (uso no humano) y `Z` (desconocido) tampoco tienen
        -- vía.
        case left(cve_ff, 1)
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
        -- `limpiar_texto` en su propio paso: dentro de `mg_por_envase` se
        -- repetiría una vez por cada patrón (~17).
        {{ limpiar_texto('presentacion') }} as presentacion_limpia
    from {{ ref('dim_ndf') }}

),

con_magnitud as (

    select
        ndf_id,
        molecula,
        via,
        {{ mg_por_envase('presentacion_limpia') }} as magnitud
    from ndf

)

select
    ndf_id,
    via,
    magnitud.mg_por_unidad,
    magnitud.unidad as unidad_mg,
    magnitud.mg_por_envase,
    if(
        molecula = 'SIN SAL' or via is null or magnitud.mg_por_unidad is null,
        null,
        concat(
            molecula, ' | ', via, ' | ',
            cast(magnitud.mg_por_unidad as string), ' ', magnitud.unidad
        )
    ) as grupo_competitivo
from con_magnitud
