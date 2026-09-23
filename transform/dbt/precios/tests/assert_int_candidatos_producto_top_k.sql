{#
    Falla si algún `producto_key` no trae exactamente 10 candidatos -el
    "Listo cuando" de ALD-88: `top_k => 10` contra una base de 180,914
    vectores nunca debería dejar a un producto con menos, y más de 10
    señalaría un bug de agregación aguas arriba.
#}
select producto_key, count(*) as n_candidatos
from {{ ref('int_candidatos_producto') }}
group by producto_key
having count(*) != 10
