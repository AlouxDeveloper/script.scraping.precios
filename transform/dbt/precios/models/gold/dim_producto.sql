{#
    Dimensión de producto de tienda (Kimball). Grano `(tienda_key, sku)`:
    es la identidad de negocio confirmada en el diagnóstico de ALD-37.
    `url_producto` no sirve como llave — cambia más seguido que el sku.

    Esta es la tabla que habilita el entity resolution con embeddings: el
    texto del producto vive aquí, una fila por producto (~160 mil), no en
    la fact (~925 mil). `ML.GENERATE_EMBEDDING` correrá sobre esta tabla.
    Generar los embeddings no es parte de este modelo.

    `producto_key` es un hash y no un entero autoincremental porque todos
    los modelos son `table` con full refresh: el hash mantiene la llave
    estable entre corridas sin estado persistente ni un `MERGE` contra la
    versión anterior de la dimensión.

    Todos los atributos son SCD1 — gana la captura más reciente. El
    desempate del `row_number` NO es decorativo: sin un orden total la
    corrida no es determinística y la dimensión cambia sola entre builds
    idénticos. El issue fija `fecha_captura desc, url_producto asc`; se
    añaden las demás columnas como desempate final para cerrar los empates
    que quedan (mismo día, misma URL, texto distinto — re-scrapeos).

    `nombre_norm` es SCD1 y no versionado: solo ~2% de los combos
    `(tienda, sku)` tienen más de un `nombre_norm`, y esa variación está
    concentrada en cutovers de parser por tienda en fechas puntuales, no en
    productos que cambiaron de identidad.

    `url_imagen_actual` es la imagen más reciente que NO sea el centinela
    `SIN_IMAGEN`, no la de la última captura: si no, un producto con imagen
    la perdería solo porque su última corrida no la trajo. NULL si nunca
    hubo imagen real.

    Sin `ndf_id` ni `match_method`: dependen del crosswalk de Knobloch, que
    no está. Nada entra a gold sin estar terminado.
#}
{{
    config(
        materialized='table',
        cluster_by=['tienda_key']
    )
}}

with precios as (

    select
        tienda,
        sku,
        producto,
        nombre_norm,
        url_producto,
        url_imagen,
        fecha_captura
    from {{ ref('precios') }}

),

atributos_actuales as (

    select
        tienda,
        sku,
        producto,
        nombre_norm,
        url_producto,
        row_number() over (
            partition by tienda, sku
            order by
                fecha_captura desc,
                url_producto asc,
                producto asc,
                nombre_norm asc
        ) as rn
    from precios

),

imagen_actual as (

    select
        tienda,
        sku,
        url_imagen as url_imagen_actual,
        row_number() over (
            partition by tienda, sku
            order by
                fecha_captura desc,
                url_producto asc,
                url_imagen asc
        ) as rn
    from precios
    where url_imagen <> 'SIN_IMAGEN'

),

observaciones as (

    select
        tienda,
        sku,
        min(fecha_captura) as fecha_primera_captura,
        max(fecha_captura) as fecha_ultima_captura,
        count(distinct fecha_captura) as dias_observados
    from precios
    group by tienda, sku

),

ensamblado as (

    select
        atributos_actuales.tienda,
        atributos_actuales.sku,
        atributos_actuales.producto,
        atributos_actuales.nombre_norm,
        atributos_actuales.url_producto as url_producto_actual,
        imagen_actual.url_imagen_actual,
        observaciones.fecha_primera_captura,
        observaciones.fecha_ultima_captura,
        observaciones.dias_observados
    from atributos_actuales
    left join imagen_actual
        on atributos_actuales.tienda = imagen_actual.tienda
        and atributos_actuales.sku = imagen_actual.sku
        and imagen_actual.rn = 1
    inner join observaciones
        on atributos_actuales.tienda = observaciones.tienda
        and atributos_actuales.sku = observaciones.sku
    where atributos_actuales.rn = 1

)

select
    -- El slug se traduce a `tienda_key` antes de hashear: la llave
    -- subrogada se construye sobre la FK de la dimensión, no sobre texto.
    {{ dbt_utils.generate_surrogate_key(['dim_tienda.tienda_key', 'ensamblado.sku']) }}
        as producto_key,
    dim_tienda.tienda_key,
    ensamblado.sku,
    ensamblado.producto,
    ensamblado.nombre_norm,
    ensamblado.url_producto_actual,
    ensamblado.url_imagen_actual,
    ensamblado.fecha_primera_captura,
    ensamblado.fecha_ultima_captura,
    ensamblado.dias_observados
from ensamblado
inner join {{ ref('dim_tienda') }} as dim_tienda
    on ensamblado.tienda = dim_tienda.tienda_slug
