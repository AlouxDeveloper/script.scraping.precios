{#
    Dimensión de producto de tienda (Kimball). Grano `(tienda_key, sku)`:
    es la identidad de negocio confirmada en el diagnóstico de ALD-37.
    `url_producto` no sirve como llave — cambia más seguido que el sku.

    Esta es la tabla que habilita el entity resolution con embeddings: el
    texto del producto vive aquí, una fila por producto (~240 mil), no en
    la fact (~1.1 millones). `AI.GENERATE_EMBEDDING` correrá sobre esta
    tabla —la función se renombró, antes era `ML.GENERATE_EMBEDDING`—, pero
    generar los embeddings no es parte de este modelo: viven en el dataset
    `precios_ml`, llaveados por el hash del texto, para que un full refresh
    de gold no los vuelva a pagar.

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

    `descripcion` es SCD1 y no versionado: solo ~2% de los combos
    `(tienda, sku)` tienen más de una `descripcion`, y esa variación está
    concentrada en cutovers de parser por tienda en fechas puntuales, no en
    productos que cambiaron de identidad. Es `producto` normalizado (sin
    acentos, vía `limpiar_texto`) y en mayúsculas -insumo del entity
    resolution contra `dim_ndf`, no un campo de exhibición.

    `url_imagen_actual` es la imagen más reciente que NO sea el centinela
    `SIN_IMAGEN`, no la de la última captura: si no, un producto con imagen
    la perdería solo porque su última corrida no la trajo. NULL si nunca
    hubo imagen real.

    `ndf_id`/`match_method`: primera pasada del entity resolution, vía el
    crosswalk `dim_puente_aportador` (Knobloch). Un producto recibe `ndf_id`
    solo cuando `(tienda_key, sku)` mapea a exactamente un `ndf_id` que
    además existe en `dim_ndf` -ambigüedad (2+ candidatos) o un `ndf_id` que
    el catálogo no tiene se quedan sin asignar, no se adivinan-. `sku` en el
    puente NO es el mismo identificador que escriben los scrapers para la
    mayoría de las tiendas (match 0-35% según tienda, ver
    `stg_puente_aportador`); por eso esta pasada cubre ~25% de `dim_producto`
    (61,085 de 240,400), no más. `match_method = 'aportadores'` marca ese
    origen; el resto queda NULL a la espera de la pasada por texto
    (embeddings contra `dim_ndf`, todavía no implementada).

    `fesa`/`yza` recibieron `aportador_clave` real en `dim_tienda` (260917,
    baja de `farmacon`/`farmesp` como tiendas propias) pero eso no movió el
    total: mismo patrón 0% que soriana (`fesa` 0/6,963, `yza` 1/4,655) —
    el sku del aportador tampoco coincide con el de esas dos tiendas.
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
        descripcion,
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
        descripcion,
        url_producto,
        row_number() over (
            partition by tienda, sku
            order by
                fecha_captura desc,
                url_producto asc,
                producto asc,
                descripcion asc
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

-- Solo candidatos con `ndf_id` real: el crosswalk trae ids que no existen
-- en `dim_ndf` (el centinela `8989898` u otros huecos del corte actual) y
-- asignarlos igual rompería cualquier join posterior contra el catálogo.
candidatos_aportador as (

    select
        dim_puente_aportador.tienda_key,
        dim_puente_aportador.sku,
        dim_puente_aportador.ndf_id
    from {{ ref('dim_puente_aportador') }} as dim_puente_aportador
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_puente_aportador.ndf_id = dim_ndf.ndf_id

),

-- Un `(tienda_key, sku)` con más de un `ndf_id` candidato es ambigüedad real
-- del aportador (ver `dim_puente_aportador`), no un caso para adivinar: se
-- descarta entero, no se toma el primero.
match_aportador as (

    select tienda_key, sku, ndf_id
    from (
        select
            tienda_key,
            sku,
            ndf_id,
            count(distinct ndf_id) over (
                partition by tienda_key, sku
            ) as n_candidatos
        from candidatos_aportador
    )
    where n_candidatos = 1

),

ensamblado as (

    select
        atributos_actuales.tienda,
        atributos_actuales.sku,
        atributos_actuales.producto,
        atributos_actuales.descripcion,
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
    match_aportador.ndf_id,
    case
        when match_aportador.ndf_id is not null then 'aportadores'
    end as match_method,
    ensamblado.producto,
    ensamblado.descripcion,
    ensamblado.url_producto_actual,
    ensamblado.url_imagen_actual,
    ensamblado.fecha_primera_captura,
    ensamblado.fecha_ultima_captura,
    ensamblado.dias_observados
from ensamblado
inner join {{ ref('dim_tienda') }} as dim_tienda
    on ensamblado.tienda = dim_tienda.tienda_slug
left join match_aportador
    on dim_tienda.tienda_key = match_aportador.tienda_key
    and ensamblado.sku = match_aportador.sku
