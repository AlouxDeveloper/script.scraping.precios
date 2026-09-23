{#
    Búsqueda vectorial de la fase catálogo completo (ALD-88). `table`, mismo
    motivo que `int_candidatos_ndf`: no vale la pena recalcular un
    `VECTOR_SEARCH` completo en cada consulta.

    Dirección producto→NDF, invertida contra la fase Sanfer -y la razón es
    que aquí la base sí está completa (`emb_ndf`, 180,914, indexada
    `TREE_AH`; la fase Sanfer usaba un recorte de ~1,400 que no calificaba
    para el índice). Con la base completa el vecino más cercano vuelve a
    significar algo: un shampoo puede tener un NDF de `division = 'NO
    FARMA'` como vecino real, no un artefacto del recorte. Y es la
    dirección que corresponde al grano de la respuesta -un listing tiene
    exactamente un `ndf_id`, así que cada uno de los ~240,400 productos
    (`emb_producto`, consulta) lo busca él mismo.

    `top_k => 10`, no 50 ni 1: el margen contra el segundo candidato
    necesita al menos dos: las guardas de magnitud pueden descartar al
    primero y entonces el segundo pasa a ser la respuesta, y
    `recall_at_10` (`rev_er_metricas`, reusado en una fase futura) es la
    métrica que dice si el método tiene techo -ninguna de las tres existe
    con `top_k => 1`.

    Mismo grano `(producto_key, ndf_id)` que `int_candidatos_ndf`, agnóstico
    a la dirección por diseño (ver su propio docstring): `int_match_ndf` se
    reusa tal cual una vez que esta fase recalibre sus umbrales (ALD-89),
    sin reescribir la lógica de decisión.

    Corrida de referencia 2026-09-22: 2,404,000 filas (240,400 producto_key
    × 10, sin huecos, ver `assert_int_candidatos_producto_top_k.sql`).
    `indexUsageMode = FULLY_USED` en
    `INFORMATION_SCHEMA.JOBS.vector_search_statistics` del job -sin
    `indexUnusedReason`, confirma que no cayó a fuerza bruta contra
    180,914 × 240,400 vectores de 768 dimensiones.
#}
{{ config(materialized='table') }}

with busqueda as (

    select
        base.ndf_id,
        query.producto_key,
        query.tienda_key,
        distance as distancia
    from vector_search(
        table {{ ref('emb_ndf') }},
        'embedding',
        table {{ ref('emb_producto') }},
        top_k => 10,
        distance_type => 'COSINE'
    )

),

atributos_producto as (

    select
        producto_key,
        {{ extraer_atributos('descripcion') }} as atributos_producto
    from {{ ref('dim_producto') }}

),

-- `limpiar_texto` aparte de `extraer_atributos`, mismo motivo que
-- `int_candidatos_ndf`: encadenarlos repetiría el regex de `limpiar_texto`
-- una vez por cada patrón que prueba `extraer_atributos` (~14).
presentacion_normalizada as (

    select
        ndf_id,
        {{ limpiar_texto('presentacion') }} as presentacion
    from {{ ref('dim_ndf') }}

),

atributos_ndf as (

    select
        ndf_id,
        {{ extraer_atributos('presentacion') }} as atributos_ndf
    from presentacion_normalizada

),

candidatos as (

    select
        busqueda.ndf_id,
        busqueda.producto_key,
        busqueda.tienda_key,
        busqueda.distancia,
        atributos_producto.atributos_producto,
        atributos_ndf.atributos_ndf,
        row_number() over (
            partition by busqueda.ndf_id, busqueda.tienda_key
            order by busqueda.distancia
        ) as rank_desde_ndf,
        row_number() over (
            partition by busqueda.producto_key
            order by busqueda.distancia
        ) as rank_desde_producto,
        lead(busqueda.distancia) over (
            partition by busqueda.producto_key
            order by busqueda.distancia
        ) - busqueda.distancia as margen_desde_mejor
    from busqueda
    inner join atributos_producto
        on atributos_producto.producto_key = busqueda.producto_key
    inner join atributos_ndf
        on atributos_ndf.ndf_id = busqueda.ndf_id

)

select
    ndf_id,
    producto_key,
    tienda_key,
    distancia,
    atributos_producto,
    atributos_ndf,
    rank_desde_ndf,
    rank_desde_producto,
    case when rank_desde_producto = 1 then margen_desde_mejor end as margen,
    rank_desde_ndf = 1 and rank_desde_producto = 1 as es_reciproco
from candidatos
