{#
    Producto de tienda con los métodos de `ndf_id` que no dependen del
    texto (`aportadores`, `ean_cruzado`). Es todo `dim_producto` menos la
    pasada vectorial (ALD-97): el entity resolution vectorial lee de aquí y
    `dim_producto` lee de él, así que la dimensión no puede ser su propia
    entrada sin cerrar un ciclo en el DAG. Vive en silver porque no es una
    tabla de consumo; el grano, las llaves y los atributos son los mismos
    que los de `dim_producto`.

    Grano `(tienda_key, sku)`:
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

    `ndf_id`/`match_method`: dos métodos que se acumulan (`match_method` no
    se reemplaza, cada método nuevo agrega un valor). Primera pasada,
    `aportadores`: vía el crosswalk `dim_puente_aportador` (Knobloch). Un producto recibe `ndf_id`
    solo cuando `(tienda_key, sku_cruce)` mapea a exactamente un `ndf_id` que
    además existe en `dim_ndf` -ambigüedad (2+ candidatos) o un `ndf_id` que
    el catálogo no tiene se quedan sin asignar, no se adivinan-. Esta pasada
    cubre ~35% de `dim_producto` (83,510 de 240,400); antes del `trim` y la
    normalización a 15 dígitos cubría ~25% (61,085) y Ahorro 0%. Soriana,
    fesa, alsuper y similares siguen en 0%: su sku en el puente es otro
    identificador, no un problema de formato. `match_method = 'aportadores'` marca ese
    origen; el resto queda NULL aquí y lo intenta la pasada vectorial en
    `dim_producto`.

    Segunda pasada, `ean_cruzado`, solo para lo que `aportadores` no tocó (ni
    asignó ni dejó ambiguo: un producto con candidatos en el puente de su
    tienda no se revisa). El sku es un código de barras que otra tienda sí
    tiene en el crosswalk: FESA y YZA escriben EAN-13 mientras su aportador
    usa un código interno de 5 dígitos, así que su puente propio no cruza
    pero el de Ahorro, Farmatodo, etc. sí. Regla 1: sku de 8+ dígitos sin
    ceros igual al de otra tienda; regla 2: sku de 12 dígitos igual al
    EAN-13 de otra tienda sin dígito verificador (así lo escribe
    Walmart/Aurrera); gana la 1 si tiene candidatos. En ambas, un solo
    `ndf_id` distinto o no se asigna. Se exigen 8+ dígitos porque por
    debajo son códigos internos de cada tienda que colisionan: la precisión
    medida contra los productos que ya tienen NDF de su aportador es 99.4%
    con 8+ dígitos y 0-17% con 7 o menos (la vigila
    `assert_dim_producto_ean_precision`). Recupera 13,040 productos: fesa
    6,348, yza 4,051, aurrera 1,123, walmart 852, comer 495. Lo que sigue
    sin match (soriana, alsuper, similares y el marketplace no
    farmacéutico de walmart/aurrera) no tiene un código común y queda para
    los métodos de texto.

    `sku_cruce`: columna temporal, solo para el join contra el puente; NO
    sale en la tabla. `dim_producto.sku` se conserva tal como lo extrae el
    scraper (sin relleno ni cambio de dígitos). El puente
    (`dim_puente_aportador.sku`) vive a 15 dígitos, así que aquí se rellena
    con ceros a la izquierda a 15 para poder compararlos: un mismo código
    aparece en las tiendas con y sin ceros (UPC-12 vs EAN-13, o
    `0730170642921`), y sin normalizar Ahorro cruzaba 0% y Farmalisto 0%.
    Antes de rellenar se quitan los ceros a la izquierda: desde febrero 2026
    San Pablo escribe el sku con relleno a 18 dígitos (`000000000070007232`)
    y sin quitarlos esos 6,011 productos quedaban fuera del cruce (0% desde
    febrero); con el `ltrim` cruzan 4,893. Los sku que siguen midiendo más de
    15 caracteres sin ceros (llegan a 24) se descartan del cruce: no existen
    en el puente, y `lpad` los truncaría y produciría cruces falsos. Un sku
    de puros ceros también queda fuera. Rellenar puede juntar dos sku distintos de la dimensión en un
    mismo `sku_cruce` (mismo código con y sin ceros); ambos reciben el
    mismo `ndf_id`, sin duplicar filas porque `match_aportador` es único
    por `(tienda_key, sku)`.

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

-- Claves propias del crosswalk: un producto con al menos un candidato en el
-- puente de SU tienda ya fue decidido por `aportadores` (asignado, o
-- ambiguo a propósito); el cruce por EAN no lo revisa para no pisar esa
-- decisión ni desambiguarla adivinando.
claves_propias as (

    select distinct tienda_key, sku
    from candidatos_aportador

),

-- Puente de TODAS las tiendas en forma de código de barras, para el cruce
-- por EAN (`ean_cruzado`). `llave12` es el EAN-13 sin dígito verificador:
-- Walmart/Aurrera escriben el sku de 12 dígitos así. Se exigen 8+ dígitos
-- porque por debajo los códigos son internos de cada tienda y colisionan
-- entre tiendas (precisión medida 0-17% con 7 dígitos o menos, 99.4% con 8+).
puente_ean as (

    select
        tienda_key,
        ndf_id,
        ltrim(sku, '0') as llave,
        if(length(ltrim(sku, '0')) = 13, substr(ltrim(sku, '0'), 1, 12), null)
            as llave12
    from candidatos_aportador
    where length(ltrim(sku, '0')) >= 8

),

ensamblado as (

    select
        atributos_actuales.tienda,
        atributos_actuales.sku,
        ltrim(atributos_actuales.sku, '0') as sku_sin_ceros,
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

),

-- Primera pasada: `aportadores`. `sku_cruce` es el sku sin ceros a la
-- izquierda antes de medir (el relleno de San Pablo a 18 dígitos no es un
-- largo natural), NULL si lo que queda excede 15 caracteres o es vacío.
con_aportadores as (

    select
        -- El slug se traduce a `tienda_key` antes de hashear: la llave
        -- subrogada se construye sobre la FK de la dimensión, no sobre
        -- texto.
        {{ dbt_utils.generate_surrogate_key(['dim_tienda.tienda_key', 'ensamblado.sku']) }}
            as producto_key,
        dim_tienda.tienda_key,
        ensamblado.sku,
        ensamblado.sku_sin_ceros,
        match_aportador.ndf_id,
        claves_propias.sku is not null as tiene_candidato_propio,
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
        and case
            when length(ensamblado.sku_sin_ceros) between 1 and 15
                then lpad(ensamblado.sku_sin_ceros, 15, '0')
        end = match_aportador.sku
    left join claves_propias
        on dim_tienda.tienda_key = claves_propias.tienda_key
        and case
            when length(ensamblado.sku_sin_ceros) between 1 and 15
                then lpad(ensamblado.sku_sin_ceros, 15, '0')
        end = claves_propias.sku

),

-- Segunda pasada: `ean_cruzado`, solo para lo que `aportadores` no tocó.
-- Regla 1: el sku (8+ dígitos, sin ceros) es igual al de un producto del
-- puente de OTRA tienda. Regla 2: el sku mide 12 dígitos y es el EAN-13 de
-- otra tienda sin su dígito verificador. Gana la regla 1 si tiene
-- candidatos; con la regla ganadora, un solo `ndf_id` distinto o nada.
candidatos_ean as (

    select con_aportadores.producto_key, 1 as regla, puente_ean.ndf_id
    from con_aportadores
    inner join puente_ean
        on con_aportadores.sku_sin_ceros = puente_ean.llave
        and con_aportadores.tienda_key != puente_ean.tienda_key
    where con_aportadores.ndf_id is null
        and not con_aportadores.tiene_candidato_propio
        and length(con_aportadores.sku_sin_ceros) >= 8

    union all

    select con_aportadores.producto_key, 2 as regla, puente_ean.ndf_id
    from con_aportadores
    inner join puente_ean
        on con_aportadores.sku_sin_ceros = puente_ean.llave12
        and con_aportadores.tienda_key != puente_ean.tienda_key
    where con_aportadores.ndf_id is null
        and not con_aportadores.tiene_candidato_propio
        and length(con_aportadores.sku_sin_ceros) = 12

),

match_ean as (

    select producto_key, ndf_id
    from (
        select
            producto_key,
            regla,
            ndf_id,
            count(distinct ndf_id) over (
                partition by producto_key, regla
            ) as n_candidatos,
            min(regla) over (partition by producto_key) as regla_ganadora
        from (select distinct producto_key, regla, ndf_id from candidatos_ean)
    )
    where regla = regla_ganadora and n_candidatos = 1

)

select
    con_aportadores.producto_key,
    con_aportadores.tienda_key,
    con_aportadores.sku,
    coalesce(con_aportadores.ndf_id, match_ean.ndf_id) as ndf_id,
    case
        when con_aportadores.ndf_id is not null then 'aportadores'
        when match_ean.ndf_id is not null then 'ean_cruzado'
    end as match_method,
    con_aportadores.producto,
    con_aportadores.descripcion,
    con_aportadores.url_producto_actual,
    con_aportadores.url_imagen_actual,
    con_aportadores.fecha_primera_captura,
    con_aportadores.fecha_ultima_captura,
    con_aportadores.dias_observados
from con_aportadores
left join match_ean
    on con_aportadores.producto_key = match_ean.producto_key
