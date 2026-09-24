{#
    El candidato rank 1 de cada producto con las señales que usa la regla
    de decisión (ALD-93): marca, distancia, margen, guarda de magnitudes,
    división del NDF y si la tienda/división está en `cuarentena_forzada`.
    Grano `producto_key`, solo productos con candidato.

    Separado de `int_match_ndf` para que la calibración
    (`rev_er_calibracion`) evalúe la regla sobre las mismas señales que
    producción; la regla en sí está en `macros/decision_vectorial.sql`.
    `view`: se lee pocas veces y recalcularla cuesta segundos.

    `marca_ok`: todas las palabras de la marca del NDF (`dim_ndf.producto`
    normalizado con `limpiar_texto`) aparecen en la descripción. Exigir
    solo la primera sube el volumen 6% pero baja FARMA de 0.953 a 0.942.
#}
{{ config(materialized='view') }}

with candidatos as (

    select
        c.producto_key,
        c.ndf_id,
        c.distancia,
        c.margen,
        dim_ndf.division,
        dim_tienda.tienda_slug,
        split({{ limpiar_texto('dim_ndf.producto') }}, ' ') as marca_norm,
        split({{ limpiar_texto('int_producto.descripcion') }}, ' ')
            as descripcion_norm,
        {{ guarda_magnitudes('c.atributos_producto', 'c.atributos_ndf') }}
            as guarda_ok
    from {{ ref('int_candidatos_producto') }} as c
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_ndf.ndf_id = c.ndf_id
    inner join {{ ref('int_producto') }} as int_producto
        on int_producto.producto_key = c.producto_key
    inner join {{ ref('dim_tienda') }} as dim_tienda
        on dim_tienda.tienda_key = int_producto.tienda_key
    where c.rank_desde_producto = 1

)

select
    producto_key,
    ndf_id,
    distancia,
    margen,
    division,
    guarda_ok,
    not exists (
        select 1
        from unnest(marca_norm) as palabra
        where palabra not in unnest(descripcion_norm)
    ) as marca_ok,
    (
        false
        {%- for estrato in var('cuarentena_forzada', []) %}
        or (
            tienda_slug = '{{ estrato.tienda }}'
            and division = '{{ estrato.division }}'
        )
        {%- endfor %}
    ) as es_cuarentena_forzada
from candidatos
