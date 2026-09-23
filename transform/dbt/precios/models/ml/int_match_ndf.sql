{#
    Decisión por producto de la fase Sanfer (ALD-73), colapsando los
    candidatos de `int_candidatos_ndf` (búsqueda NDF→producto). Grano
    `producto_key`, universo completo de `producto_candidato_sanfer`
    (240,400 filas) -no solo los que aparecieron como candidatos de algún
    NDF-: para la mayor parte del universo la respuesta correcta es que
    no hay `ndf_id` de Sanfer, y `sin_match` lo dice explícito en vez de
    desaparecer la fila.

    **Las guardas de magnitud se aplican antes de rankear, no después**
    (`guarda_magnitudes`, ALD-69/ALD-73): si el candidato más cercano
    declara 500 mg contra los 750 mg del producto, se descarta esa fila
    entera y se rankea de nuevo entre los que sí sobreviven -el segundo
    candidato pasa a ser la respuesta, con su propia distancia y su
    propio margen, no la distancia ni el margen del primero.

    **Respaldo cuando NINGÚN candidato sobrevive la guarda**
    (`mejor_bruto`): se reporta igual el mejor candidato bruto de
    `int_candidatos_ndf` (su `rank_desde_producto = 1` original, con su
    propia distancia/margen/reciprocidad, ya calculados ahí -no se
    recalculan), marcado `guarda_ok = false`. Es lo que permite que la
    decisión mande esa fila a `cuarentena` en vez de perderla en
    `sin_match`: la tabla de decisión del issue incluye "falla la guarda"
    como motivo de cuarentena, no de descarte -hay un candidato real, solo
    que su magnitud no cuadra, y eso lo revisa una persona, no se ignora.

    `margen`: distancia del segundo candidato menos la del primero, ENTRE
    LOS QUE SOBREVIVEN LA GUARDA (o, en el respaldo, entre los candidatos
    brutos -mismo campo que ya trae `int_candidatos_ndf`). `NULL` si el
    producto solo tiene un candidato en su grupo -no hay "segundo" contra
    qué medir la soledad de la respuesta-, y por diseño eso nunca cumple
    `margen >= delta_min`: sin un segundo candidato no se puede confirmar
    qué tan sola está la respuesta, así que cae a `cuarentena` en vez de
    `vectorial` aunque la distancia sea excelente.

    `es_reciproco`/`guarda_ok` se cargan del candidato elegido tal cual
    los computó `int_candidatos_ndf` -`es_reciproco` es una propiedad del
    par `(producto_key, ndf_id)` sobre el candidato universo completo, no
    cambia por filtrar magnitudes, así que no hace falta recalcularla.

    **Umbrales por bucket** (`bucket_tienda`, ALD-84), no globales ni por
    tienda individual -`vars` de ALD-68 (`tau_alto_a/b`, `tau_bajo_a/b`,
    `delta_min`, este último sí global: verificado en ALD-68 que la resta
    cancela el sesgo de estilo de tienda).

    **Regla de decisión** (en este orden; la primera que aplica gana):

    1. `sin_match` si no hay ningún candidato -ni guardado ni bruto- para
       el producto, o si el mejor candidato (bruto) queda por encima de
       `tau_bajo[bucket]`.
    2. `vectorial` si el candidato elegido pasa la guarda, es recíproco,
       su distancia es `<= tau_alto[bucket]` y su margen es
       `>= delta_min`.
    3. `cuarentena` en cualquier otro caso dentro de `tau_bajo[bucket]`
       -falla el margen, la guarda o la reciprocidad, pero la distancia
       todavía es lo bastante buena para valer una revisión manual.
#}
{{ config(materialized='table') }}

with candidatos as (

    select
        c.producto_key,
        c.ndf_id,
        c.distancia,
        c.es_reciproco,
        c.rank_desde_producto,
        c.margen as margen_bruto,
        {{ guarda_magnitudes('c.atributos_producto', 'c.atributos_ndf') }}
            as guarda_ok
    from {{ ref('int_candidatos_ndf') }} as c

),

rankeado_guardado as (

    select
        producto_key,
        ndf_id,
        distancia,
        es_reciproco,
        true as guarda_ok,
        row_number() over (
            partition by producto_key order by distancia
        ) as rn,
        lead(distancia) over (
            partition by producto_key order by distancia
        ) - distancia as margen
    from candidatos
    where guarda_ok

),

mejor_guardado as (

    select producto_key, ndf_id, distancia, margen, es_reciproco, guarda_ok
    from rankeado_guardado
    where rn = 1

),

-- Respaldo: el mejor candidato SIN filtrar por guarda, ya calculado por
-- int_candidatos_ndf. Solo se usa cuando mejor_guardado no tiene fila
-- para ese producto (ninguna magnitud sobrevivió).
mejor_bruto as (

    select
        producto_key,
        ndf_id,
        distancia,
        margen_bruto as margen,
        es_reciproco,
        guarda_ok
    from candidatos
    where rank_desde_producto = 1

),

-- mejor_bruto ya cubre todo producto_key con al menos un candidato -es
-- rank_desde_producto = 1 de int_candidatos_ndf, que existe para todos
-- ellos-, así que ancla el join: mejor_guardado es un subconjunto suyo,
-- nunca trae un producto_key que bruto no tenga.
mejor_candidato as (

    select
        bruto.producto_key,
        coalesce(guardado.ndf_id, bruto.ndf_id) as ndf_id,
        coalesce(guardado.distancia, bruto.distancia) as distancia,
        coalesce(guardado.margen, bruto.margen) as margen,
        coalesce(guardado.es_reciproco, bruto.es_reciproco) as es_reciproco,
        coalesce(guardado.guarda_ok, bruto.guarda_ok) as guarda_ok
    from mejor_bruto as bruto
    left join mejor_guardado as guardado
        on guardado.producto_key = bruto.producto_key

),

universo as (

    select
        producto_candidato_sanfer.producto_key,
        {{ bucket_tienda('dim_tienda.tienda_slug') }} as bucket
    from {{ ref('producto_candidato_sanfer') }} as producto_candidato_sanfer
    inner join {{ ref('dim_tienda') }} as dim_tienda
        on dim_tienda.tienda_key = producto_candidato_sanfer.tienda_key

),

-- decision se calcula aparte del select final -no en línea- para poder
-- anular ndf_id/distancia/margen/guarda_ok/es_reciproco cuando el
-- resultado es sin_match sin repetir el case completo cinco veces: ndf_id
-- es NULL exactamente cuando decision = 'sin_match', el test que pide el
-- issue, y esto lo garantiza por construcción en vez de depender de que
-- las dos expresiones nunca se desincronicen.
decidido as (

    select
        universo.producto_key,
        universo.bucket,
        mejor_candidato.ndf_id,
        mejor_candidato.distancia,
        mejor_candidato.margen,
        mejor_candidato.guarda_ok,
        mejor_candidato.es_reciproco,
        case
            when mejor_candidato.ndf_id is null then 'sin_match'
            when mejor_candidato.distancia > (
                case
                    when universo.bucket = 'A' then {{ var('tau_bajo_a') }}
                    else {{ var('tau_bajo_b') }}
                end
            ) then 'sin_match'
            when
                mejor_candidato.distancia <= (
                    case
                        when universo.bucket = 'A' then {{ var('tau_alto_a') }}
                        else {{ var('tau_alto_b') }}
                    end
                )
                and mejor_candidato.margen >= {{ var('delta_min') }}
                and mejor_candidato.guarda_ok
                and mejor_candidato.es_reciproco
                then 'vectorial'
            else 'cuarentena'
        end as decision
    from universo
    left join mejor_candidato
        on mejor_candidato.producto_key = universo.producto_key

)

select
    producto_key,
    case when decision != 'sin_match' then ndf_id end as ndf_id,
    case when decision != 'sin_match' then distancia end as distancia,
    case when decision != 'sin_match' then margen end as margen,
    case when decision != 'sin_match' then guarda_ok end as guarda_ok,
    case when decision != 'sin_match' then es_reciproco end as es_reciproco,
    decision
from decidido
