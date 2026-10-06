{#
    Todo lo que no entró a `precios`, con el motivo y los valores
    originales del CSV (los `*_raw`, no los tipados): el punto de esta
    tabla es ver qué traía la fila cuando no pasó el filtro, sin tener
    que ir a bronce a mano.
#}
{{
    config(
        materialized='table',
        partition_by={
            'field': 'mes',
            'data_type': 'date',
            'granularity': 'month'
        },
        cluster_by=['motivo_descarte']
    )
}}

select
    coalesce(motivo_descarte, 'DUPLICADO') as motivo_descarte,
    tienda,
    mes,
    fecha_captura,
    url_producto,
    producto,
    sku_raw,
    precio_actual_raw,
    precio_oferta_raw,
    fecha_captura_raw,
    tienda_raw,
    calidad_flags,
    _archivo_origen,
    _fila_num,
    _ingestado_en
from {{ ref('stg_precios') }}
where motivo_descarte is not null or rn > 1
