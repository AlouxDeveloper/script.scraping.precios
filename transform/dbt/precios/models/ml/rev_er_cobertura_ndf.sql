{#
    Cobertura por NDF del catálogo completo (ALD-90), reporte de cierre de
    la fase: de los 180,914 `ndf_id`, cuáles reciben al menos un producto
    de tienda y por qué método. Grano `ndf_id`.

    Tres métodos reales hoy -`match_method` está pensado para acumular, no
    para reemplazarse (ver `dim_producto.sql`)-:

    - `aportadores`: `dim_producto.match_method = 'aportadores'` ya
      resuelto, el crosswalk de Knobloch (~25% de `dim_producto`).
    - `ean_cruzado`: `dim_producto.match_method = 'ean_cruzado'`, el EAN del
      producto coincide con el de otra tienda en el crosswalk (ver
      `dim_producto.sql`). Va después de `aportadores` en la prioridad.
    - `vectorial`: `int_match_ndf.decision = 'vectorial'` (ALD-90),
      solo cuenta si ese `producto_key` NO tenía ya un `ndf_id` de
      aportadores -aportadores es la fuente confirmada, no se pisa-.

    `manual` (ALD-74, seed `er_manual.csv`) todavía no existe -esta vista
    no tiene esa columna, no un valor `NULL` disfrazado de método real; se
    agrega cuando ALD-74 se implemente, no antes.

    **No incluye alcanzabilidad.** Si un `ndf_id` nunca aparece con
    `tiene_match = false`, puede ser un error del matcher o puede ser que
    su marca simplemente no se vende en ninguna de las 19 tiendas -esa
    partición del denominador es un análisis aparte
    (`entity_resolution/sql/16_denominador_alcanzable_catalogo.sql`, las
    tablas `rev_ndf_alcanzabilidad_catalogo`/`rev_ndf_sin_oferta_catalogo`
    en `precios_ml`, fuera del grafo de dbt a propósito, mismo patrón que
    ALD-82): unir aquí infla el grano sin necesidad -es una pregunta
    binaria por marca (30,836 valores distintos), no por `ndf_id`.
#}
{{ config(materialized='view') }}

with metodo_aportadores as (

    select distinct ndf_id
    from {{ ref('dim_producto') }}
    where match_method = 'aportadores'

),

metodo_ean as (

    select distinct ndf_id
    from {{ ref('dim_producto') }}
    where match_method = 'ean_cruzado'

),

metodo_vectorial as (

    -- distinct: un mismo ndf_id puede llegar por vectorial desde varias
    -- tiendas (varios producto_key), cuenta una sola vez para cobertura.
    select distinct ndf_id
    from {{ ref('int_match_ndf') }}
    where decision = 'vectorial'

)

select
    dim_ndf.ndf_id,
    dim_ndf.laboratorio,
    dim_ndf.corporacion,
    dim_ndf.division,
    case
        when metodo_aportadores.ndf_id is not null then 'aportadores'
        when metodo_ean.ndf_id is not null then 'ean_cruzado'
        when metodo_vectorial.ndf_id is not null then 'vectorial'
    end as metodo,
    metodo_aportadores.ndf_id is not null
        or metodo_ean.ndf_id is not null
        or metodo_vectorial.ndf_id is not null as tiene_match
from {{ ref('dim_ndf') }} as dim_ndf
left join metodo_aportadores
    on metodo_aportadores.ndf_id = dim_ndf.ndf_id
left join metodo_ean
    on metodo_ean.ndf_id = dim_ndf.ndf_id
left join metodo_vectorial
    on metodo_vectorial.ndf_id = dim_ndf.ndf_id
