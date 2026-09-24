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

    Las señales del candidato vienen de `int_candidato_evaluado` y la
    regla de `macros/decision_vectorial.sql`, compartidas con la vista de
    calibración `rev_er_calibracion`.

    - **Marca por palabra, todas las palabras** (ver
      `int_candidato_evaluado`).
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

-- La regla se aplica sobre `int_candidato_evaluado` a solas: junto a
-- `int_producto` sus columnas (`ndf_id`) serían ambiguas. Un producto sin
-- candidato no está ahí y queda `sin_match` en el join.
with decidido as (

    select
        producto_key,
        ndf_id,
        distancia,
        margen,
        guarda_ok,
        marca_ok,
        {{ decision_vectorial(var('tau_farma'), var('tau_no_farma')) }}
            as decision
    from {{ ref('int_candidato_evaluado') }}

)

-- Las columnas del candidato se anulan en sin_match: ndf_id es NULL
-- exactamente cuando decision = 'sin_match', por construcción.
select
    int_producto.producto_key,
    if(decidido.decision != 'sin_match', decidido.ndf_id, null) as ndf_id,
    if(decidido.decision != 'sin_match', decidido.distancia, null)
        as distancia,
    if(decidido.decision != 'sin_match', decidido.margen, null) as margen,
    if(decidido.decision != 'sin_match', decidido.guarda_ok, null)
        as guarda_ok,
    if(decidido.decision != 'sin_match', decidido.marca_ok, null)
        as marca_ok,
    coalesce(decidido.decision, 'sin_match') as decision
from {{ ref('int_producto') }} as int_producto
left join decidido
    on decidido.producto_key = int_producto.producto_key
