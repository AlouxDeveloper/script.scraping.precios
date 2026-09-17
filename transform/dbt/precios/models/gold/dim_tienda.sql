{#
    Dimensión de tiendas: catálogo propio del proyecto, no el de ningún
    scraper. 19 filas, sin clustering (cabe en un bloque).

    `tienda_slug` es el punto de traducción entre el scraping y el modelo:
    es lo que trae `precios_silver.precios` y lo único que cruza el histórico
    ya cargado en BigQuery con este catálogo.

    Los IDs numéricos que ya escriben algunos scrapers (`2` Benavides, `12`
    Walmart, `16` Aurrera, `17` ISSEG, `22` Alsuper) NO se reusan como
    `tienda_key`: son un catálogo ajeno, incompleto y con huecos. Quedan
    donde están, en `tienda_raw` de bronce.

    `aportador_clave` traduce contra `puente_aportador_ext` (crosswalk
    tienda-sku-ndf). `fesa` = aportador `P1` ("Farmacias Especializadas") y
    `yza` = aportador `A8` ("Farmacon"): mismo negocio, nombre distinto
    entre el scraping y el crosswalk de Knobloch — confirmado por Knobloch,
    no una coincidencia de texto. Solo `similares` queda NULL (sin
    aportador todavía). Hasta 260916 `farmacon`/`farmesp` vivían como dos
    `tienda_key` propios (20, 21) sin tienda scrapeada detrás; se dieron de
    baja al confirmarse el mapeo real y esos dos números no se reusan
    (ver la regla del seed `tiendas`).
#}

select
    tienda_key,
    tienda_slug,
    tienda_nombre,
    aportador_clave
from {{ ref('tiendas') }}
