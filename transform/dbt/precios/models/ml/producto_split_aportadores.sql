{#
    Split determinístico de calibración/holdout sobre el set completo de
    aportadores (ALD-65), grano `producto_key`. `dim_producto` filtrado a
    `match_method = 'aportadores'` -61,085 filas, ground truth objetivo del
    entity resolution- partido en dos mitades con
    `mod(abs(farm_fingerprint(producto_key)), 2)`.

    El set es el completo, no el recorte Sanfer -esa es la decisión de este
    issue-. La geometría que se calibra -qué tan lejos queda la
    `descripcion` de tienda de la `presentacion` de su NDF- no depende del
    laboratorio, y limitar la calibración a Sanfer dejaría del orden de
    decenas por tienda, un intervalo de confianza inservible (misma lógica
    del corte n=300 de ALD-58, con la n dividida entre 19). Los umbrales se
    calibran contra las 61,085 filas y se aplican al recorte Sanfer.

    Sin estado, igual que `producto_key` es un hash y no un entero
    autoincremental (ver `dim_producto.sql`): la partición se deriva de la
    llave, no se guarda en ningún lado, y dos corridas -o un full refresh
    completo de gold- dan el mismo split.

    Calibración es donde se prueba todo: variantes de texto, umbrales por
    tienda, guardas. Holdout NO se toca hasta el final de cada fase y se
    mide una sola vez -medirlo más de una vez lo convierte en calibración:
    cada vistazo filtra una decisión y el número deja de ser una estimación
    honesta de qué pasará con datos nuevos-.

    Corrida de referencia 2026-09-22: 61,085 filas -30,374 calibración /
    30,711 holdout, 49.72%/50.28%-, balanceado dentro de un par de puntos
    porcentuales en las 13 tiendas con match `aportadores` (48.13% en
    `farmatodo` a 51.02% en `aurrera`; `guadalajara` es la más grande con
    10,909 filas y 50.05%/49.95%). `yza` cae en n=1 -no hay split posible
    con una sola fila, no es un desbalance real. Subconjunto Sanfer -vía
    `dim_ndf.laboratorio = 'SANFER'`-: 706 calibración / 804 holdout de
    1,510 filas, suficiente para verificar la fase 1 en cada mitad.
#}
{{ config(materialized='view') }}

select
    producto_key,
    tienda_key,
    case
        when mod(abs(farm_fingerprint(producto_key)), 2) = 0 then 'calibracion'
        else 'holdout'
    end as split
from {{ ref('int_producto') }}
where match_method = 'aportadores'
