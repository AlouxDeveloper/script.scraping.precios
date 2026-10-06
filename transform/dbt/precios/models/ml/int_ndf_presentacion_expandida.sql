{#
    Presentación del catálogo NDF con las abreviaturas expandidas (ALD-94),
    insumo de la variante `v4` de `texto_er_ndf`. El catálogo escribe
    `TABL`, `CRA`, `PZS`... y la tienda la palabra completa: en los pares
    verdaderos del crosswalk `TABL` falta del lado tienda en el 99.6% de
    los casos, así que el embedding comparaba dos idiomas distintos.

    Vive aparte y no en `dim_ndf` a propósito: `dim_ndf` conserva la
    presentación original del catálogo, y esta columna es una
    transformación al servicio del embedding, no un atributo de negocio.

    Se parte la presentación en tramos alternos de letras y de no-letras
    (`\p{L}+|[^\p{L}]+`) y solo se reemplazan los tramos de letras que
    coinciden completos con el seed. Así `100MG/ML` o `G.I` quedan intactos
    sin necesidad de un `\b` por abreviatura, y al volver a unir los tramos
    en orden se conserva la puntuación y el espaciado originales.
#}
{{ config(materialized='table') }}

with tramos as (

    select
        dim_ndf.ndf_id,
        dim_ndf.presentacion,
        tramo,
        posicion
    from {{ ref('dim_ndf') }} as dim_ndf
    cross join
        unnest(regexp_extract_all(dim_ndf.presentacion, r'\p{L}+|[^\p{L}]+'))
        as tramo with offset as posicion

)

select
    tramos.ndf_id,
    any_value(tramos.presentacion) as presentacion,
    string_agg(
        coalesce(abreviaturas.expansion, tramos.tramo), ''
        order by tramos.posicion
    ) as presentacion_expandida
from tramos
left join {{ ref('abreviaturas_ndf') }} as abreviaturas
    on abreviaturas.abreviatura = upper(tramos.tramo)
group by tramos.ndf_id
