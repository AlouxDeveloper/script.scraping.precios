{#
    Curva de calibración de los `tau` del entity resolution vectorial
    (ALD-99; reemplaza a `rev_er_metricas_catalogo`, que medía la regla
    anterior con reciprocidad y sin marca). Aplica la regla vigente
    (`macros/decision_vectorial.sql`, la misma que `int_match_ndf`) sobre
    el split de calibración de `producto_split_aportadores`, barriendo el
    `tau` de 0 a 0.20 en pasos de 0.005 con el resto de la regla fijo,
    salvo `cuarentena_forzada`, que no se aplica (ver el CTE `evaluado`).

    Grano `(division, tau)`. `division` es la del NDF candidato, porque es
    la que elige qué `tau` se aplica; `tau` se barre para las dos
    divisiones a la vez (`tau_farma = tau_no_farma = tau`) y cada fila
    solo cuenta los candidatos de su división, así que las dos curvas no
    se contaminan.

    Uso: al cambiar el texto vectorizado (`variante_ndf`) o la regla, se
    busca en cada división el `tau` más alto con `precision` sobre el
    objetivo (0.95 FARMA, 0.85 NO FARMA) y se fija en `dbt_project.yml`.
    Con v4: FARMA 0.9599 en 0.10, NO FARMA 0.8521 en 0.04 (ALD-95); tras
    reconstruir el índice en ALD-99, 0.9604 y 0.8512 -`TREE_AH` es
    aproximado y el índice nuevo mueve unos pocos vecinos-.
    El holdout (`split = 'holdout'`) no se toca aquí.

    `recall_at_10` es la fracción del universo de calibración cuyo NDF
    correcto sale entre los 10 candidatos (85.13% con v4): el techo del
    método, igual para todas las filas de la división.
#}
{{ config(materialized='view') }}

with universo as (

    select
        split.producto_key,
        int_producto.ndf_id as ndf_id_verdadero
    from {{ ref('producto_split_aportadores') }} as split
    inner join {{ ref('int_producto') }} as int_producto
        on int_producto.producto_key = split.producto_key
    where split.split = 'calibracion'

),

recall as (

    select
        dim_ndf.division,
        safe_divide(countif(candidatos.ndf_id is not null), count(*))
            as recall_at_10
    from universo
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_ndf.ndf_id = universo.ndf_id_verdadero
    -- Grano (producto_key, ndf_id) en los candidatos: a lo más una fila
    -- por producto, no duplica el universo.
    left join {{ ref('int_candidatos_producto') }} as candidatos
        on candidatos.producto_key = universo.producto_key
        and candidatos.ndf_id = universo.ndf_id_verdadero
    group by dim_ndf.division

),

evaluado as (

    -- `cuarentena_forzada` se neutraliza: es un override por estrato que
    -- se decidió auditando huérfanos (ALD-96), no algo que el tau deba
    -- absorber. En calibración los estratos forzados aciertan bien
    -- (fahorro NO FARMA con crosswalk no es el de las medias Daonsa) y
    -- aplicarlo bajaría la curva de NO FARMA de 0.851 a 0.840 en 0.04.
    select
        evaluado.* replace (false as es_cuarentena_forzada),
        evaluado.ndf_id = universo.ndf_id_verdadero as es_correcto
    from universo
    inner join {{ ref('int_candidato_evaluado') }} as evaluado
        on evaluado.producto_key = universo.producto_key

),

decidido as (

    select
        tau,
        division,
        es_correcto,
        {{ decision_vectorial('tau', 'tau') }} as decision
    from evaluado
    cross join unnest(generate_array(0.0, 0.2, 0.005)) as tau

)

select
    decidido.division,
    round(decidido.tau, 3) as tau,
    countif(decidido.decision = 'vectorial') as n_vectorial,
    countif(decidido.decision = 'vectorial' and decidido.es_correcto)
        as n_correctos,
    safe_divide(
        countif(decidido.decision = 'vectorial' and decidido.es_correcto),
        countif(decidido.decision = 'vectorial')
    ) as precision,
    countif(decidido.decision = 'cuarentena') as n_cuarentena,
    any_value(recall.recall_at_10) as recall_at_10
from decidido
left join recall
    on recall.division = decidido.division
group by decidido.division, round(decidido.tau, 3)
