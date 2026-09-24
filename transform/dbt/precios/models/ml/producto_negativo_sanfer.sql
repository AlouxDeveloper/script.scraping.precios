{#
    Set de negativos de la fase Sanfer (ALD-87), derivado gratis del
    crosswalk de aportadores -reemplaza el etiquetado manual a mano que
    ALD-59 pausó: la sección farmacia curada de cada tienda daba menos de 40
    candidatos de abarrote/limpieza por tienda y, sobre todo, no medía el
    riesgo real-. Alimenta `fp_negativos`: qué tan seguido la búsqueda
    vectorial les asignaría un `ndf_id` de Sanfer que no les toca, la
    métrica que evita que la curva de calibración salga optimista.

    Grano `producto_key`, restringido a `match_method = 'aportadores'`: es
    la única fuente de verdad objetiva hoy -si el crosswalk ya confirmó el
    `ndf_id` de un producto, se sabe con certeza su laboratorio y división-.
    Ambos criterios exigen `laboratorio <> 'SANFER'`: un producto sí-Sanfer
    en división 'NO FARMA' -90 de los 1,389 `ndf_id` del recorte, ver
    `04_conteos_recorte_sanfer.sql`- no es un negativo, es Sanfer real que
    no es fármaco, y no se ignora:

    - `es_negativo_laboratorio`: el `ndf_id` conocido es de un laboratorio
      distinto de Sanfer. Negativo duro.
    - `es_negativo_division`: además de laboratorio distinto de Sanfer, cae
      en división 'NO FARMA'. Segundo corte de contraste -por eso siempre
      implica `es_negativo_laboratorio`, no es independiente de él-.

    Lo que este set NO cubre: un producto sí-Sanfer cuya presentación
    correcta no está en el catálogo -cae en cuarentena, no aquí- y un match
    de similitud alta con producto equivocado dentro del propio recorte
    Sanfer -ningún umbral lo detecta; lo atacan la guarda de magnitudes y la
    reciprocidad, aparte-.

    Corrida de referencia 2026-09-22: 59,575 filas -todas con
    `es_negativo_laboratorio`, 23,382 además con `es_negativo_division`- sobre
    13 de las 19 tiendas -las 6 restantes no tienen ningún match
    `aportadores` hoy, ver `dim_producto`-. Excluir los 31 productos sí-Sanfer
    en 'NO FARMA' movió el total de 59,606 a 59,575: la corrección no vacía
    el set. El tamaño alcanza para un intervalo de Wilson al 95% muy por
    debajo de 1pp de ancho sobre `fp_negativos`; `guadalajara` domina con
    10,676 y `yza` es la cola con 1 fila, arrastrando la misma
    desproporción por tienda que el resto del match de aportadores.
#}
{{ config(materialized='view') }}

with match_conocido as (

    select
        dim_producto.producto_key,
        dim_producto.tienda_key,
        dim_ndf.laboratorio,
        dim_ndf.division
    from {{ ref('int_producto') }} as dim_producto
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_producto.ndf_id = dim_ndf.ndf_id
    where dim_producto.match_method = 'aportadores'

)

select
    producto_key,
    tienda_key,
    upper(laboratorio) <> 'SANFER' as es_negativo_laboratorio,
    upper(laboratorio) <> 'SANFER'
        and upper(division) = 'NO FARMA' as es_negativo_division
from match_conocido
where upper(laboratorio) <> 'SANFER'
