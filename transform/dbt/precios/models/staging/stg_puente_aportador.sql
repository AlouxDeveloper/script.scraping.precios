{#
    Vista de staging del puente aportador: aquí se deriva `sku` y se decide
    qué del origen se conserva. Bronce lo guarda todo en STRING a propósito;
    el tipado vive en dbt, junto a la regla que lo justifica.

    - `sku`: `correlativo` normalizado a 15 dígitos: `trim` y `lpad` con
      ceros. El origen lo rellena de dos formas según el aportador: con
      ceros (`000000000000001`) o con espacios (`S1` y `I4`, p. ej.
      `           6929`). Antes solo se quitaban ceros a la izquierda, así
      que el relleno de espacios sobrevivía y ningún sku de Ahorro ni de
      Farmalisto cruzaba con `dim_producto` (0% de cobertura); con `trim`
      el cruce de Ahorro pasó a ~93%. Se deja a 15 dígitos y no sin ceros
      porque `dim_producto` calcula su `sku_cruce` con la misma forma; ver
      ahí el porqué. `lpad` trunca lo que excede el largo destino y el
      máximo en origen es 15, así que no recorta nada (lo vigila un test
      de largo en el yml).

      `correlativo = '000000000000000'` es un centinela de "sin sku
      conocido" (6 filas en el corte 260910; las que traen `ndf_id` lo tienen en
      `'8989898'`, otro centinela del aportador): `sku` queda NULL, no 15 ceros.

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

    -- `nullif` convierte en NULL el centinela de puros ceros (o un
    -- `correlativo` vacío, que `lpad` también rellena a 15 ceros). En
    -- `ndf_id` evita que `regexp_replace` devuelva cadena vacía.
    nullif(lpad(trim(correlativo), 15, '0'), '000000000000000') as sku,
    nullif(regexp_replace(ndf_id, r'^0+', ''), '') as ndf_id,

    producto,
    descripcion

from {{ source('bronce', 'puente_aportador_ext') }}
