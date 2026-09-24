{#
    Guarda contra la regresión silenciosa que dejó a Farmacias del Ahorro en
    0% de cobertura del crosswalk: el aportador `S1` rellena el correlativo
    con espacios y, sin `trim`, ningún sku de Ahorro igualaba al de
    `dim_producto`. Nada falló: el join simplemente no encontraba filas.

    Falla si menos de la mitad de los productos de `fahorro` recibió
    `ndf_id` por `aportadores` (hoy ~93%). El 50% es un piso holgado, no la
    meta: solo detecta que el cruce se rompió, no que empeoró un poco.
#}
select
    count(*) as productos,
    countif(dim_producto.match_method = 'aportadores') as con_aportadores
from {{ ref('dim_producto') }} as dim_producto
inner join {{ ref('dim_tienda') }} as dim_tienda using (tienda_key)
where dim_tienda.tienda_slug = 'fahorro'
having countif(dim_producto.match_method = 'aportadores') < 0.5 * count(*)
