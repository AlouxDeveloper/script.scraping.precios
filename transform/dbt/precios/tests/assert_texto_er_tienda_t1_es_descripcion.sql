{#
    Fija el default de texto_er_tienda.sql: sin `variante_tienda` en vars,
    t1 debe ser exactamente `descripcion`, columna por columna, para las
    240,400 filas de dim_producto.
#}

select
    int_texto_er_tienda.producto_key,
    int_texto_er_tienda.texto,
    dim_producto.descripcion
from {{ ref('int_texto_er_tienda') }} as int_texto_er_tienda
inner join {{ ref('dim_producto') }} as dim_producto
    on dim_producto.producto_key = int_texto_er_tienda.producto_key
where int_texto_er_tienda.texto is distinct from dim_producto.descripcion
