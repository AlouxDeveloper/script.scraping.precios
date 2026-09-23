{#
    Universo candidato de la búsqueda vectorial NDF→producto de la fase
    Sanfer (ALD-87). El prefiltro por marca que este modelo iba a aplicar se
    descartó en ALD-83 -recall 93.51%, bajo el corte de 0.95; la causa es
    estructural, casi la mitad del catálogo Sanfer son nombres genéricos con
    un código de laboratorio pegado que ninguna tienda escribe, no un
    problema de normalización de texto-, así que hoy es `dim_producto`
    completo (240,400 filas) y la precisión recae entera en el umbral y la
    guarda de magnitudes.

    Se deja separado de `dim_producto` -no se referencia directo desde la
    búsqueda vectorial- para que, si un prefiltro distinto se retoma más
    adelante, el cambio quede en este modelo y no en cada consumidor.

    Corrida de referencia 2026-09-22: 240,400 filas -mismo conteo que
    `dim_producto`, confirma que el pass-through no pierde ni agrega filas.
#}
{{ config(materialized='view') }}

select
    producto_key,
    tienda_key
from {{ ref('dim_producto') }}
