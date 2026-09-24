{#
    Curva de precisión/cobertura de la fase Sanfer (ALD-66), `view` -el
    prefijo `rev_` marca vista operativa de revisión, no un modelo que
    alimenta otro modelo. Grano `(variante_ndf, variante_tienda,
    tienda_key, umbral, guardas_activas)`.

    **El universo es la calibración, no el catálogo ni la tienda enteros.**
    Solo `producto_split_aportadores` con `split = 'calibracion'`
    (ALD-65): productos con `ndf_id` confirmado por el crosswalk, la única
    verdad objetiva disponible. Holdout no se toca aquí -se mide una sola
    vez, al final de la fase-. Esto es una decisión de alcance deliberada,
    no un descuido: significa que `cobertura`/`cobertura_ndf` miden qué
    tan bien funciona el método sobre el ~25% de `dim_producto` que ya
    tiene verdad conocida, no sobre el 75% sin etiquetar que es el objetivo
    real de producción -no hay con qué medir precisión sobre ese 75% antes
    de decidir un umbral, y ese es exactamente el problema que este issue
    resuelve primero.

    Dentro de calibración, cada fila es positivo (`es_positivo_sanfer`,
    `ndf_id` conocido de laboratorio Sanfer -FARMA o NO FARMA, ver
    ALD-87-) o negativo (cualquier otro laboratorio, la misma regla que
    `producto_negativo_sanfer`, derivada aquí en vez de por join extra
    porque ya se necesita `dim_ndf.laboratorio` para otra cosa).

    `variante_ndf`/`variante_tienda` son constantes -`var()`, con default
    a la variante activa hoy (v1/t1)-, no una dimensión calculada: hoy solo
    existe una corrida de `int_candidatos_ndf`. Si se corre una variante
    distinta, hay que reconstruir `emb_texto`/`emb_producto`/`emb_ndf`/
    `int_candidatos_ndf` para esa variante primero y correr esta vista con
    `--vars` etiquetando la misma combinación -la columna es la etiqueta de
    qué corrida representa la tabla en ese momento, dbt no la deriva sola.
    Comparar variantes es apilar corridas (`UNION ALL` a mano o en un
    snapshot), no una sola consulta.

    **Decisión por producto** (su candidato `rank_desde_producto = 1` en
    `int_candidatos_ndf`, si tiene alguno):

    - `rechazado`: sin candidato en absoluto, o `distancia > umbral`.
    - `banda_gris`: `distancia <= umbral` pero, con las guardas activas,
      `pasa_guardas` es falso -la distancia dice que sí, la guarda no está
      seguro; va a revisión manual, no a rechazo automático-.
    - `aceptado`: el resto -`distancia <= umbral` y (guardas apagadas o
      `pasa_guardas` verdadero)-.

    Con `guardas_activas = false` nunca hay `banda_gris`: es el punto de
    comparación "¿ayudan las guardas o solo quitan cobertura?".

    **Métricas** (todas sobre el universo de calibración de esa
    `tienda_key`, salvo donde se dice lo contrario):

    - `recall_at_k`: de los positivos, a cuántos el `ndf_id` correcto les
      aparece en CUALQUIER posición de sus candidatos (no solo el primero).
      No depende de `umbral` ni `guardas_activas` -es el techo del método,
      se mira antes que cualquier otra métrica de esta vista.
    - `precision_at_1`: de los positivos, a cuántos su candidato más
      cercano (rank 1) SÍ es el `ndf_id` correcto. Tampoco depende de
      `umbral`/`guardas_activas` -es la línea base sin corte.
    - `precision`: de los positivos con bucket `aceptado`, qué fracción su
      candidato aceptado es correcto. Esta sí varía con `umbral` y
      `guardas_activas` -es la que se optimiza.
    - `cobertura`: fracción de TODO el universo de calibración (positivos
      y negativos) que cae en `aceptado`.
    - `cobertura_ndf`: de los 1,389 `ndf_id` de Sanfer (`emb_ndf_sanfer`),
      cuántos tienen al menos un candidato `aceptado` en esta tienda -sin
      distinguir si ese candidato es o no el correcto: en producción no hay
      verdad contra qué comparar, así que esta métrica es sobre
      asignación, no sobre acierto. Denominador = tamaño de
      `emb_ndf_sanfer` (1,389 hoy, calculado, no fijo), no los 734
      "alcanzables" de ALD-82 -esa tabla (`rev_ndf_alcanzabilidad_sanfer`)
      vive fuera del grafo de dbt a propósito (ver
      `07_denominador_alcanzable_sanfer.sql`) y no se referencia aquí.
    - `fp_negativos`: de los negativos, qué fracción cae en `aceptado` -un
      producto de otro laboratorio recibiendo un `ndf_id` de Sanfer que no
      le toca. Es la contraparte de `precision`: la precisión sola se
      puede inflar subiendo el umbral, esto no se puede fingir.
    - `n_calibracion`/`n_aceptado`/`n_rechazado`/`n_banda_gris`: los
      conteos crudos detrás de `cobertura` y `precision`.
      `n_aceptado + n_rechazado + n_banda_gris = n_calibracion` por
      construcción -el test de esquema lo verifica.
#}
{{ config(materialized='view') }}

with rango_distancia as (

    -- Techo dinámico, no un número fijo: si `int_candidatos_ndf` cambia de
    -- variante o de `top_k`, el rango de distancias se mueve solo y los
    -- pasos del umbral lo siguen sin editar este modelo.
    select ceiling(max(distancia) * 100) / 100 as umbral_max
    from {{ ref('int_candidatos_ndf') }}

),

umbrales as (

    -- `round`: generate_array acumula el paso en binario y arrastra
    -- residuo de punto flotante (0.03 sale como 0.030000000000000002);
    -- redondear a milésimas lo deja limpio sin perder resolución del paso
    -- real (0.005).
    select round(umbral, 3) as umbral
    from rango_distancia, unnest(generate_array(0.0, umbral_max, 0.005)) as umbral

),

guardas as (

    select guardas_activas
    from unnest([true, false]) as guardas_activas

),

universo as (

    -- Grano `producto_key`: el universo de calibración completo (positivo
    -- y negativo), con la verdad de laboratorio ya resuelta.
    select
        split.producto_key,
        split.tienda_key,
        int_producto.ndf_id as ndf_id_verdadero,
        upper(dim_ndf.laboratorio) = 'SANFER' as es_positivo_sanfer
    from {{ ref('producto_split_aportadores') }} as split
    inner join {{ ref('int_producto') }} as int_producto
        on int_producto.producto_key = split.producto_key
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_ndf.ndf_id = int_producto.ndf_id
    where split.split = 'calibracion'

),

candidato_top as (

    -- Solo el mejor candidato por producto: la decisión de aceptar,
    -- rechazar o mandar a banda gris se toma sobre el rank 1, no sobre
    -- los 50 candidatos completos.
    select
        producto_key,
        ndf_id as ndf_id_candidato,
        distancia,
        {{ pasa_guardas('atributos_producto', 'atributos_ndf', 'es_reciproco') }}
            as pasa_guardas
    from {{ ref('int_candidatos_ndf') }}
    where rank_desde_producto = 1

),

recall_logrado as (

    -- distinct: un positivo puede tener el ndf_id correcto en más de una
    -- posición del top-k solo si hubiera duplicados, lo cual no debería
    -- pasar (grano (producto_key, ndf_id) único en int_candidatos_ndf),
    -- pero el distinct deja la unión con `universo` sin riesgo de fila
    -- repetida de todas formas.
    select distinct candidatos.producto_key
    from {{ ref('int_candidatos_ndf') }} as candidatos
    inner join universo
        on universo.producto_key = candidatos.producto_key
        and universo.ndf_id_verdadero = candidatos.ndf_id

),

decision_base as (

    select
        universo.producto_key,
        universo.tienda_key,
        universo.es_positivo_sanfer,
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

    count(*) as n_calibracion,
    countif(bucket = 'aceptado') as n_aceptado,
    countif(bucket = 'rechazado') as n_rechazado,
    countif(bucket = 'banda_gris') as n_banda_gris,

    safe_divide(countif(bucket = 'aceptado'), count(*)) as cobertura,

    safe_divide(
        count(distinct case when bucket = 'aceptado' then ndf_id_candidato end),
        (select count(*) from {{ ref('emb_ndf_sanfer') }})
    ) as cobertura_ndf,

    safe_divide(
        countif(es_positivo_sanfer and recall_logrado),
        countif(es_positivo_sanfer)
    ) as recall_at_k,

    safe_divide(
        countif(es_positivo_sanfer and top1_correcto),
        countif(es_positivo_sanfer)
    ) as precision_at_1,

    safe_divide(
        countif(es_positivo_sanfer and bucket = 'aceptado' and top1_correcto),
        countif(es_positivo_sanfer and bucket = 'aceptado')
    ) as precision,

    safe_divide(
        countif(not es_positivo_sanfer and bucket = 'aceptado'),
        countif(not es_positivo_sanfer)
    ) as fp_negativos

from decision_por_umbral
group by tienda_key, umbral, guardas_activas
