{#
    Curva de precisión/cobertura de la fase catálogo completo (ALD-89),
    gemela de `rev_er_metricas` (ALD-66) pero sobre `int_candidatos_producto`
    (ALD-88) en vez de `int_candidatos_ndf`: mismo universo de calibración
    (`producto_split_aportadores`, ALD-65), misma mecánica de umbral ×
    guardas, misma razón para no tocar holdout.

    **Por qué es un modelo aparte y no el mismo con un `ref` distinto.** El
    concepto de "negativo" que traía `rev_er_metricas` -`es_positivo_sanfer`,
    "otro laboratorio no debería recibir ningún candidato Sanfer"- no aplica
    aquí: con el catálogo completo, CUALQUIER laboratorio es un match
    válido, así que todo producto de `producto_split_aportadores` es
    "positivo" en el sentido de que ya tiene una verdad conocida
    (`ndf_id_verdadero`) contra la cual medir, sin importar de qué
    laboratorio sea. `fp_negativos` no tiene equivalente limpio: no hay un
    "no debería matchear con nada de este catálogo" derivable del
    crosswalk -el crosswalk solo confirma matches positivos.

    **La limitación de negativos que pide el issue queda así, no
    resuelta.** El único contraste de categoría disponible sin revisión
    manual es `es_no_farma` (la división del `ndf_id_verdadero`, no del
    candidato): productos genuinamente NO FARMA sirven de sanity check -si
    el método confundiera categorías, su precisión caería ahí primero-. Es
    señal, no medición de negativos: un producto que no está en el catálogo
    en ninguna forma (ni FARMA ni NO FARMA) sigue sin etiqueta, cae en
    cuarentena y no en un bucket medible aquí. `es_no_farma` es un corte del
    grano (no una columna de metadata), simétrico a `guardas_activas`, para
    poder comparar sus curvas lado a lado sin una fila extra por combinación.

    **Hallazgo de la recalibración (corrida 2026-09-22, `NOT es_no_farma`,
    guardas activas):** el objetivo de precisión 0.95 SÍ cruza cuando se
    mide solo contra la verdad FARMA -bucket A en 0.022 (0.9619, n=2,624),
    bucket B en 0.018 (0.9333, n=30, débil por tamaño de muestra)- pero
    NUNCA cruza si se mide contra el universo mixto (máximo 0.923 en
    bucket A, cualquier `umbral`): la densidad de 180,914 candidatos hace
    que el vecino más cercano de un producto NO FARMA con frecuencia sea un
    NDF real, no un artefacto, y ese acierto "equivocado de categoría" es
    justo lo que `es_no_farma` aísla. `delta_min = 0.008` (ALD-68) se
    verificó sobre esta misma verdad FARMA y **aguantó sin cambios**: 56%
    de los "confiados pero equivocados" atrapados al costo de solo 4.0% de
    los aciertos (mejor relación que el 10.7% de Sanfer, no peor). `tau_bajo`
    se fijó IGUAL a `tau_alto` en los dos buckets -a diferencia de Sanfer,
    donde había holgura hasta 0.055-: con la base completa, ensanchar
    `tau_bajo` más allá de `tau_alto` dispara la banda gris de inmediato
    (bucket B pasa de 728 a 2,881 filas con solo 0.004 de holgura), y el
    mínimo posible ya es 2,573 filas -por encima del presupuesto de ~2,000
    de Sanfer-, así que no hay margen para ensanchar sin disparar aún más
    la carga de revisión manual.
#}
{{ config(materialized='view') }}

with rango_distancia as (

    select ceiling(max(distancia) * 100) / 100 as umbral_max
    from {{ ref('int_candidatos_producto') }}

),

umbrales as (

    select round(umbral, 3) as umbral
    from rango_distancia, unnest(generate_array(0.0, umbral_max, 0.005)) as umbral

),

guardas as (

    select guardas_activas
    from unnest([true, false]) as guardas_activas

),

universo as (

    -- Grano `producto_key`: todo el universo de calibración, cualquier
    -- laboratorio -aquí no hay filtro de positivo/negativo por lab, ver
    -- docstring.
    select
        split.producto_key,
        split.tienda_key,
        dim_producto.ndf_id as ndf_id_verdadero,
        upper(dim_ndf.division) = 'NO FARMA' as es_no_farma
    from {{ ref('producto_split_aportadores') }} as split
    inner join {{ ref('int_producto') }} as dim_producto
        on dim_producto.producto_key = split.producto_key
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_ndf.ndf_id = dim_producto.ndf_id
    where split.split = 'calibracion'

),

candidato_top as (

    select
        producto_key,
        ndf_id as ndf_id_candidato,
        distancia,
        {{ pasa_guardas('atributos_producto', 'atributos_ndf', 'es_reciproco') }}
            as pasa_guardas
    from {{ ref('int_candidatos_producto') }}
    where rank_desde_producto = 1

),

recall_logrado as (

    select distinct candidatos.producto_key
    from {{ ref('int_candidatos_producto') }} as candidatos
    inner join universo
        on universo.producto_key = candidatos.producto_key
        and universo.ndf_id_verdadero = candidatos.ndf_id

),

decision_base as (

    select
        universo.producto_key,
        universo.tienda_key,
        universo.es_no_farma,
        candidato_top.ndf_id_candidato,
        candidato_top.distancia,
        candidato_top.pasa_guardas,
        recall_logrado.producto_key is not null as recall_logrado,
        candidato_top.ndf_id_candidato = universo.ndf_id_verdadero
            as top1_correcto
    from universo
    left join candidato_top
        on candidato_top.producto_key = universo.producto_key
    left join recall_logrado
        on recall_logrado.producto_key = universo.producto_key

),

decision_por_umbral as (

    select
        decision_base.*,
        umbrales.umbral,
        guardas.guardas_activas,
        case
            when decision_base.ndf_id_candidato is null then 'rechazado'
            when decision_base.distancia > umbrales.umbral then 'rechazado'
            when guardas.guardas_activas and not decision_base.pasa_guardas
                then 'banda_gris'
            else 'aceptado'
        end as bucket
    from decision_base
    cross join umbrales
    cross join guardas

)

select
    '{{ var("variante_ndf", "v1") }}' as variante_ndf,
    '{{ var("variante_tienda", "t1") }}' as variante_tienda,
    tienda_key,
    umbral,
    guardas_activas,
    es_no_farma,

    count(*) as n_calibracion,
    countif(bucket = 'aceptado') as n_aceptado,
    countif(bucket = 'rechazado') as n_rechazado,
    countif(bucket = 'banda_gris') as n_banda_gris,

    safe_divide(countif(bucket = 'aceptado'), count(*)) as cobertura,

    safe_divide(countif(recall_logrado), count(*)) as recall_at_k,

    safe_divide(countif(top1_correcto), count(*)) as precision_at_1,

    safe_divide(
        countif(bucket = 'aceptado' and top1_correcto),
        countif(bucket = 'aceptado')
    ) as precision

from decision_por_umbral
group by tienda_key, umbral, guardas_activas, es_no_farma
