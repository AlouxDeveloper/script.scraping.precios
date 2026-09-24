{#
    Decisión por producto sobre el catálogo completo: colapsa el candidato
    rank 1 de `int_candidatos_producto` (búsqueda producto→NDF) en una fila
    por `producto_key`, universo completo de `int_producto` (240,400
    filas). Para la mayor parte del universo la respuesta correcta es que
    no hay `ndf_id`, y `sin_match` lo dice explícito en vez de desaparecer
    la fila.

    Decide para todos los productos, también los que ya tienen crosswalk:
    así la calibración compara contra la verdad conocida. `dim_producto`
    solo toma `vectorial` donde el crosswalk y el EAN no asignaron nada, y
    `ndf_cuarentena` solo la `cuarentena` de esos mismos productos.

    **Regla vigente: marca + margen por división (ALD-93).** Reemplaza la
    de umbrales por bucket de estilo de tienda (ALD-89/90). El diagnóstico
    del 2026-09-23 midió que, de los productos del crosswalk cuyo NDF
    correcto sale en rank 1, la regla anterior aceptaba 1 de cada 6: `tau`
    (0.022) se llevaba el 96% de las pérdidas. La señal que sí separa
    aciertos de errores es que la marca del NDF aparezca en la
    descripción de la tienda; sin ella la precisión ronda 0.5.

    En este orden; la primera que aplica gana:

    1. `sin_match` si no hay candidato, si la distancia supera el `tau` de
       la división del NDF (`tau_farma` / `tau_no_farma`) o si alguna
       palabra de la marca no aparece en la descripción.
    2. `vectorial` si además `margen >= delta_min`, la guarda de
       magnitudes pasa y la combinación tienda/división no está en
       `cuarentena_forzada` (ALD-96, ver el comentario del var).
    3. `cuarentena` en otro caso: la marca y la distancia cuadran, pero
       falla el margen, la guarda o la tienda está en cuarentena forzada. Es la banda gris que revisa el
       método 3, no un rechazo.

    Decisiones medidas sobre el split de calibración, que no conviene
    re-derivar:

    - **Marca por palabra, todas las palabras.** `marca_norm` es
      `dim_ndf.producto` pasado por `limpiar_texto` y partido en palabras;
      exigir solo la primera sube el volumen 6% pero baja FARMA de 0.953 a
      0.942.
    - **Sin reciprocidad.** Contradice la relación N:1 (una tienda con dos
      listings del mismo producto obliga a que uno falle) y compra +0.65 pp
      de precisión a cambio de -7.4% de volumen.
    - **La guarda ya no re-rankea.** Antes descartaba candidatos antes de
      elegir y el segundo pasaba a ser la respuesta; ahora el candidato es
      siempre el rank 1 y la guarda solo decide entre `vectorial` y
      `cuarentena`. Con la marca presente sí separa: en FARMA lo que la
      falla acierta 0.899 contra 0.961 de lo que la pasa.
    - **Genéricos fuera.** El catálogo nombra los genéricos como
      `PARACETAMOL GI ALL` (molécula + GI + laboratorio) y la tienda nunca
      escribe el laboratorio, así que la marca no aparece y caen a
      `sin_match`. La alternativa molécula + dosis + piezas exactas mide
      0.13 de precisión (0.39 con margen): el issue la condicionaba a 0.95
      y no se activa. Elegir el laboratorio correcto es trabajo del
      método 3.

    `margen` es el que ya calcula `int_candidatos_producto` (distancia del
    segundo candidato menos la del primero). `NULL` si no hay segundo, y
    por diseño eso nunca cumple `margen >= delta_min`: cae a `cuarentena`.
#}
{{ config(materialized='table') }}

with candidatos as (

    select
        c.producto_key,
        c.ndf_id,
        c.distancia,
        c.margen,
        dim_ndf.division,
        dim_tienda.tienda_slug,
        split({{ limpiar_texto('dim_ndf.producto') }}, ' ') as marca_norm,
        split({{ limpiar_texto('int_producto.descripcion') }}, ' ')
            as descripcion_norm,
        {{ guarda_magnitudes('c.atributos_producto', 'c.atributos_ndf') }}
            as guarda_ok
    from {{ ref('int_candidatos_producto') }} as c
    inner join {{ ref('dim_ndf') }} as dim_ndf
        on dim_ndf.ndf_id = c.ndf_id
    inner join {{ ref('int_producto') }} as int_producto
        on int_producto.producto_key = c.producto_key
    inner join {{ ref('dim_tienda') }} as dim_tienda
        on dim_tienda.tienda_key = int_producto.tienda_key
    where c.rank_desde_producto = 1

),

evaluado as (

    select
        producto_key,
        ndf_id,
        distancia,
        margen,
        guarda_ok,
        not exists (
            select 1
            from unnest(marca_norm) as palabra
            where palabra not in unnest(descripcion_norm)
        ) as marca_ok,
        distancia <= (
            case
                when division = 'FARMA' then {{ var('tau_farma') }}
                else {{ var('tau_no_farma') }}
            end
        ) as distancia_ok,
        (
            false
            {%- for estrato in var('cuarentena_forzada', []) %}
            or (
                tienda_slug = '{{ estrato.tienda }}'
                and division = '{{ estrato.division }}'
            )
            {%- endfor %}
        ) as es_cuarentena_forzada
    from candidatos

),

-- decision se calcula aparte del select final para poder anular las
-- columnas del candidato cuando es sin_match sin repetir el case: ndf_id
-- es NULL exactamente cuando decision = 'sin_match' por construcción.
decidido as (

    select
        int_producto.producto_key,
        evaluado.ndf_id,
        evaluado.distancia,
        evaluado.margen,
        evaluado.guarda_ok,
        evaluado.marca_ok,
        case
            when evaluado.ndf_id is null then 'sin_match'
            when not (evaluado.distancia_ok and evaluado.marca_ok)
                then 'sin_match'
            when evaluado.margen >= {{ var('delta_min') }}
                and evaluado.guarda_ok
                and not evaluado.es_cuarentena_forzada
                then 'vectorial'
            else 'cuarentena'
        end as decision
    from {{ ref('int_producto') }} as int_producto
    left join evaluado
        on evaluado.producto_key = int_producto.producto_key

)

select
    producto_key,
    case when decision != 'sin_match' then ndf_id end as ndf_id,
    case when decision != 'sin_match' then distancia end as distancia,
    case when decision != 'sin_match' then margen end as margen,
    case when decision != 'sin_match' then guarda_ok end as guarda_ok,
    case when decision != 'sin_match' then marca_ok end as marca_ok,
    decision
from decidido
