{#
    Dimensión del catálogo NDF (Kimball). `ref('stg_ndf')` sin
    transformación: el tipado ya vive en staging y aquí no hay nada que
    derivar, solo materializar y clusterizar.

    Grano: una fila por `ndf_id`, que en este catálogo equivale a producto
    + presentación. NO es a nivel marca: `DIGESAN GRAG. 6` y
    `DIGESAN JBE 15 ML` son dos `ndf_id` distintos, no variantes de uno.
    Confirmado en el archivo: 180,914 `ndf_id` únicos contra 30,836 valores
    de `producto`.

    La jerarquía comercial se queda plana. `corporacion`, `laboratorio`,
    `producto` (la marca) y `molecula` son columnas de esta tabla, no
    dimensiones aparte: con 3,553 corporaciones y 5,410 moléculas,
    snowflakear solo agrega joins sin ahorrar almacenamiento medible.

    Choque de nombres a tener presente: `producto` aquí es la marca
    comercial del catálogo; `dim_producto.producto` es el nombre del
    listing en la tienda. Son cosas distintas y por eso viven en
    dimensiones distintas.

    Clusterizada por `corporacion`: es el corte natural de análisis y la
    columna de mayor cardinalidad útil para podar escaneos.
#}
{{
    config(
        materialized='table',
        cluster_by=['corporacion']
    )
}}

select
    ndf_id,
    fecha_lanzamiento,
    std_fac,
    presentacion,
    producto,
    descripcion,
    cve_laboratorio,
    laboratorio,
    corporacion,
    cve_mg,
    cve_genero,
    genero,
    cve_ct,
    cve_ff,
    forma_farmaceutica_n3,
    molecula,
    division
from {{ ref('stg_ndf') }}
