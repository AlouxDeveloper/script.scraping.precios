{#
    Búsqueda vectorial de la fase Sanfer (ALD-72). `table`: cuesta un
    `VECTOR_SEARCH` completo, no vale la pena recalcularla en cada consulta.

    Dirección NDF→producto -`emb_producto` (240,400, indexada `TREE_AH`)
    como base, `emb_ndf_sanfer` (~1,400) como consulta-, no al revés. Tres
    razones:

    1. La métrica de negocio es por NDF -"¿este NDF tiene producto en
       alguna tienda?"-. Buscando por NDF ninguno queda sin evaluar; al
       revés, un NDF que ningún producto elige en su top-k desaparece sin
       decir si es porque no se vende o porque perdió por poco.
    2. Un NDF tiene de 1 a 19+ productos correctos, uno por tienda, así que
       su presupuesto de candidatos tiene que ser generoso. Al revés, con
       una base recortada a ~1,400 NDF de Sanfer, todo producto de tienda
       -incluido un shampoo- recibiría vecinos Sanfer, y el umbral
       cargaría solo con todo el trabajo.
    3. El lado NDF está homologado; el lado tienda es el ruidoso. Conviene
       gastar el presupuesto de búsqueda tirando una red amplia desde el
       lado limpio.

    `top_k => 50` es global, no por tienda -`VECTOR_SEARCH` no admite
    prefiltro sobre columnas de la tabla base, solo sobre la subconsulta
    que la define (ver "Filter on Partitioning Column" en la documentación
    de BigQuery), y particionar `emb_producto` por `tienda_key` en 19
    subconsultas por cada NDF de consulta es más caro que sobrepedir. Se
    resuelve con `top_k` generoso y `rank_desde_ndf` particionado por
    `(ndf_id, tienda_key)` aguas abajo -walmart (67k listings) no le quita
    candidatos a sanpablo dentro del mismo NDF, cada tienda rankea los
    suyos aparte.

    Coseno, no euclidiana: importa la dirección del vector -de qué habla el
    texto-, no su magnitud, que en embeddings de texto corto varía con la
    longitud de la cadena.

    Grano `(producto_key, ndf_id)`, agnóstico a la dirección -decisión
    deliberada: la fase del catálogo completo busca producto→NDF y reusa
    este modelo de decisión tal cual, solo cambia de dónde salen los
    candidatos (`emb_ndf` completo como base, `emb_producto` como
    consulta). Por eso la tabla ya trae los atributos de
    `extraer_atributos` de los dos lados calculados -para que el modelo de
    decisión no vuelva a parsear texto-, no solo del lado NDF.

    Dos rankings, derivados con window functions, sin materializar ninguna
    matriz:

    - `rank_desde_ndf`: el mejor candidato de cada tienda para ese NDF
      (partición `ndf_id, tienda_key`). Mide cobertura -¿este NDF aparece
      en esta tienda?-.
    - `rank_desde_producto`: el mejor NDF para ese producto (partición
      `producto_key`). Mide precisión -¿a qué NDF real pertenece este
      producto?-.
    - `margen`: distancia del segundo candidato menos la del primero, por
      producto -solo en la fila `rank_desde_producto = 1`, NULL en el
      resto (no hay "segundo mejor" que reportar dos veces) y también NULL
      si el producto no tiene segundo candidato. Importa tanto como la
      distancia: un producto puede tener su mejor candidato a distancia
      excelente y aun así ser un match malo si el segundo está
      prácticamente igual de cerca -y eso pasa justo entre dos
      presentaciones del mismo medicamento-. La distancia dice qué tan
      bueno es el mejor; el margen dice qué tan sola está esa respuesta.
    - `es_reciproco`: `rank_desde_ndf = 1` y `rank_desde_producto = 1` a la
      vez -el producto y el NDF se eligen mutuamente como mejor candidato.

    Atributos de presentación: `dim_producto.descripcion` ya viene
    normalizada por `limpiar_texto` (ver su propio docstring); del lado NDF
    se aplica `limpiar_texto` aquí sobre `presentacion` -mismo tratamiento
    en los dos lados antes de `extraer_atributos`, para que "0.5 ML" y
    "0.5ML" no diverjan por una diferencia de formato que no es de
    presentación.

    Corrida de referencia 2026-09-22: 69,450 filas (1,389 `ndf_id` × 50,
    sin huecos), 2.6 GiB procesados, 15.1 s. `distancia` en [0, 0.165].
    `indexUsageMode = FULLY_USED` en
    `INFORMATION_SCHEMA.JOBS.vector_search_statistics` del job -sin
    `indexUnusedReason`, ese campo solo aparece si el índice NO se usó.
    Cobertura por tienda -`ndf_id` con al menos un candidato de esa
    tienda-: de 303/1,389 (`sanpablo`) a 1,375/1,389 (`fahorro`), ninguna
    tienda en cero.
#}
{{ config(materialized='table') }}

with busqueda as (

    select
        query.ndf_id,
        base.producto_key,
        base.tienda_key,
        distance as distancia
    from vector_search(
        table {{ ref('emb_producto') }},
        'embedding',
        table {{ ref('emb_ndf_sanfer') }},
        'embedding',
        top_k => 50,
        distance_type => 'COSINE'
    )

),

atributos_producto as (

    select
        producto_key,
        {{ extraer_atributos('descripcion') }} as atributos_producto
    from {{ ref('dim_producto') }}

),

-- `limpiar_texto` aparte de `extraer_atributos`, en dos pasos: si se
-- encadenaran en una sola expresión, el regex completo de `limpiar_texto`
-- se repetiría una vez por cada patrón que prueba `extraer_atributos`
-- (~14), y el SQL compilado dejaría de ser legible.
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
