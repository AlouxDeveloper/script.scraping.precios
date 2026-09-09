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
#}

select
    tienda_key,
    tienda_slug,
    tienda_nombre
from {{ ref('tiendas') }}
