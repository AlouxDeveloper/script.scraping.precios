{#
    Guarda de precisión del método `ean_cruzado`. Para los productos que ya
    tienen `ndf_id` por `aportadores` (verdad de su propio aportador), repite
    la regla 1 del cruce por EAN -sku de 8+ dígitos sin ceros contra el puente
    de OTRAS tiendas, un solo `ndf_id`- y compara. Es la medición con la que
    se decidió el corte de 8 dígitos (99.4% de acierto; con 7 o menos baja a
    0-17% porque colisionan códigos internos de cada tienda).

    Falla si el acierto cae bajo 97%: un puente nuevo con códigos que
    colisionan, o un corte de dígitos mal puesto, degradaría en silencio el
    método sin tocar ningún otro test.
#}
with verdad as (

    select
        producto_key,
        tienda_key,
        ltrim(sku, '0') as llave,
        ndf_id
    from {{ ref('dim_producto') }}
    where match_method = 'aportadores'
        and length(ltrim(sku, '0')) >= 8

),

puente as (

    select
        dim_puente_aportador.tienda_key,
        ltrim(dim_puente_aportador.sku, '0') as llave,
        dim_puente_aportador.ndf_id
    from {{ ref('dim_puente_aportador') }} as dim_puente_aportador
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_puente_aportador.ndf_id = dim_ndf.ndf_id

),

prediccion as (

    select
        verdad.producto_key,
        verdad.ndf_id as ndf_verdad,
        any_value(puente.ndf_id) as ndf_predicho
    from verdad
    inner join puente
        on verdad.llave = puente.llave
        and verdad.tienda_key != puente.tienda_key
    group by verdad.producto_key, verdad.ndf_id
    having count(distinct puente.ndf_id) = 1

)

select
    count(*) as casos,
    countif(ndf_predicho = ndf_verdad) as aciertos
from prediccion
having count(*) > 0
    and countif(ndf_predicho = ndf_verdad) < 0.97 * count(*)
