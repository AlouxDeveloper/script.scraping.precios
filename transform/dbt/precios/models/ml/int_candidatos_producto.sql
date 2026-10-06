{#
    Búsqueda vectorial de la fase catálogo completo (ALD-88). `table`: no vale la
    pena recalcular un `VECTOR_SEARCH` completo en cada consulta.

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
    necesita al menos dos, `recall_at_10` (`rev_er_calibracion`) es
    la métrica que dice si el método tiene techo (85.13% con v4), y los 10
    son la lista de la que elige el método 3 en `ndf_cuarentena` -ninguna
    de las tres existe con `top_k => 1`.

    Grano `(producto_key, ndf_id)`. `int_match_ndf` toma solo el rank 1;
    `ndf_cuarentena`, los 10.

    Corrida de referencia 2026-09-22: 2,404,000 filas (240,400 producto_key
    × 10, sin huecos, ver `assert_int_candidatos_producto_top_k.sql`).
    `indexUsageMode = FULLY_USED` en
    `INFORMATION_SCHEMA.JOBS.vector_search_statistics` del job -sin
    `indexUnusedReason`, confirma que no cayó a fuerza bruta contra
    180,914 × 240,400 vectores de 768 dimensiones.

    Antes de buscar, `avisar_indice_vectorial` emite un warning si el
    índice de `emb_ndf` no está completo (ALD-99): tras una carga nueva el
    `merge` deja unos miles de filas sin indexar que se buscan por fuerza
    bruta, lo que es aceptable; si el aviso dice 0% o sin índice, conviene
    esperar a que BigQuery termine de indexar (~10 min).
#}
{{ config(materialized='table') }}
{{ avisar_indice_vectorial([ref('emb_ndf')]) }}

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
    from {{ ref('int_producto') }}

),

-- `limpiar_texto` aparte de `extraer_atributos`: encadenarlos repetiría el regex de `limpiar_texto`
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
    rank_desde_producto,
    case when rank_desde_producto = 1 then margen_desde_mejor end as margen
from candidatos
