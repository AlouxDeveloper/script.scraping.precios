{#
    Vista de staging: tipado + derivadas + motivo de descarte. Conserva
    TODAS las filas de bronce -incluidas las descartadas- para que
    `precios` y `precios_cuarentena` puedan partir el universo sin perder
    nada.
#}

with tipado as (

    select
        tienda,
        anio_mes,
        -- El mes sale de la partición, no de la fecha: san pablo marzo se
        -- corrió el 2026-04-01 y derivarlo de la fecha lo colapsaría
        -- contra abril, perdiendo esas observaciones.
        parse_date('%Y-%m', anio_mes) as mes,
        -- Aurrera escribe el centinela "SEARCH" como sku cuando el
        -- scraper cae en la página de búsqueda, pero la URL sí trae el
        -- código real del producto. Verificado contra las filas con sku
        -- válido de aurrera: coincide en 99.99% (189,126/189,138) de los
        -- casos, así que es una fuente confiable, no una adivinanza.
        coalesce(
            sku,
            case
                when tienda = 'aurrera'
                    then regexp_extract(url_producto, r'/(\d+)(?:\?|$)')
            end
        ) as sku,
        url_producto,
        producto,
        {{ limpiar_texto('producto') }} as nombre_norm,
        -- Walmart escribe el literal "No disponible" cuando no hay imagen.
        nullif(nullif(trim(url_imagen), ''), 'No disponible') as url_imagen,
        -- El "0.00" que el scraper escribe al fallar el parseo se trata
        -- igual que un nulo.
        if(precio_actual > 0, precio_actual, null) as precio_lista,
        if(precio_oferta > 0, precio_oferta, null) as precio_oferta,
        -- Se descarta la hora: 64% del histórico no la trae y walmart es
        -- 100% sin hora.
        date(fecha_captura) as fecha_captura,
        sku_raw,
        precio_actual_raw,
        precio_oferta_raw,
        fecha_captura_raw,
        tienda_raw,
        calidad_flags,
        precio_parse_ok,
        fecha_parse_ok,
        sku_es_centinela,
        fila_vacia,
        desfase_mes,
        anio_mes_dato,
        _archivo_origen,
        _md5_origen,
        _variante_schema,
        _fila_num,
        _ingestado_en
    from {{ source('bronce', 'precios_ext') }}

),

clasificado as (

    select
        *,
        case
            when producto is null or trim(producto) = '' then 'SIN_DESCRIPCION'
            when coalesce(precio_lista, precio_oferta) is null then 'SIN_PRECIO'
            -- sku ya viene con la imputación de aurrera aplicada (ver
            -- tipado); lo que llega nulo aquí no tiene regla de rescate.
            when sku is null then 'SIN_SKU'
            else null
        end as motivo_descarte
    from tipado

),

-- El row_number solo corre sobre filas sin motivo de descarte: una fila
-- descartada no debe consumir un número de la secuencia de sus
-- duplicados válidos. `mes` y el linaje quedan fuera de la partición a
-- propósito: una fila idéntica en el resto de columnas es la misma
-- observación aunque venga de otra carpeta, y sobrevive con el `mes` de
-- la primera vez que apareció.
numerado as (

    select
        tienda,
        anio_mes,
        _archivo_origen,
        _fila_num,
        row_number() over (
            partition by
                tienda, url_producto, sku, producto, url_imagen,
                precio_lista, precio_oferta, fecha_captura
            order by mes asc, _fila_num asc
        ) as rn
    from clasificado
    where motivo_descarte is null

)

select
    clasificado.*,
    numerado.rn
from clasificado
left join numerado
    using (tienda, anio_mes, _archivo_origen, _fila_num)
