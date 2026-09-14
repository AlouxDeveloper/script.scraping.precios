{#
    Vista de staging del puente aportador: aquí se deriva `sku` y se decide
    qué del origen se conserva. Bronce lo guarda todo en STRING a propósito;
    el tipado vive en dbt, junto a la regla que lo justifica.

    - `sku`: `correlativo` sin el padding de ceros a la izquierda (15
      caracteres en origen). Mismo criterio que la imputación de sku de
      aurrera en `stg_precios`: derivada aquí, documentada aquí.
      `correlativo = '000000000000000'` es un centinela de "sin sku
      conocido" (5 filas en el corte 260910, todas con `ndf_id = '8989898'`,
      otro centinela del aportador): `sku` queda NULL, no cadena vacía.

      **Validado y NO coincide con `dim_producto.sku`.** El % de coincidencia
      por sku distinto (soriana 0%, chedraui 4%, walmart 6%, klyns 11%,
      benavides 14%) descarta un join directo `sku = sku`: `correlativo`
      trae códigos de 10 a 13 dígitos (parecen EAN/UPC del aportador) contra
      los 6-8 dígitos que escriben los scrapers como sku de tienda —
      sistemas de identificación distintos, no el mismo dato con formato
      distinto. El entity resolution real (`entity_resolution/`) va a
      necesitar matching por texto (`producto`/`descripcion` vs
      `dim_producto.descripcion`), no un join por sku.
    - `bandera`: se lee pero no se usa en el modelo de matching; se descarta
      aquí, no en bronce, para no perder el dato original de la fuente.
    - `ndf_id`: sin padding, mismo criterio que `sku`. **Validado:** contra
      `dim_ndf.ndf_id` (que llega sin padding desde `catalogos.py`), quitar
      el padding aquí recupera 102,446 filas que el join perdía en silencio
      (456,515 -> 558,961 de 951,958, ~48% -> ~59%). Es el bloqueo que
      documenta `stg_ndf` — resuelto de este lado del crosswalk.
#}

select
    aportador_clave,
    aportador,

    -- `nullif` cubre el caso borde de un `correlativo`/`ndf_id` de puros
    -- ceros: sin esto, `regexp_replace` devolvería cadena vacía en vez de
    -- NULL.
    nullif(regexp_replace(correlativo, r'^0+', ''), '') as sku,
    nullif(regexp_replace(ndf_id, r'^0+', ''), '') as ndf_id,

    producto,
    descripcion

from {{ source('bronce', 'puente_aportador_ext') }}
