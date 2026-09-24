{#
    Lado tienda vectorizado (ALD-71). `table`, no `view` -a diferencia de
    `int_texto_er_tienda`: esta es la base indexada de la fase Sanfer
    (~240,400 vectores, ~1.4 GB, muy por encima del mínimo de 10 MB que
    exige `TREE_AH`). El recorte NDF→Sanfer (8.6 MB) no se puede indexar,
    así que el índice va de este lado; el `VECTOR INDEX` en sí no vive
    aquí -es DDL aparte, versionado en
    `entity_resolution/sql/12_indice_emb_producto.sql`, porque dbt no tiene
    materialización nativa para índices vectoriales.

    `LEFT JOIN` contra `emb_texto`, no `INNER`: un `producto_key` sin
    vector tiene que sobrevivir la fila como NULL y reventar el
    `not_null(embedding)` de `_emb_producto.yml`, en vez de desaparecer en
    silencio y que la búsqueda de cobertura cuente de menos sin que nadie
    lo note (issue ALD-71: "un producto sin vector es un error, no un
    caso"). Si esto falla, el banco `emb_texto` está incompleto -falta
    correr el incremental, no arreglar este modelo.

    `producto_key` único por construcción: `dim_producto` (grano
    `producto_key`) → `int_texto_er_tienda` (mismo grano, 1:1) →
    `emb_texto` (grano `texto_hash`, y el hash del texto de tienda es
    único por `producto_key` porque `int_texto_er_tienda.hash_texto` ya lo
    es).
#}
{{ config(materialized='table') }}

select
    p.producto_key,
    p.tienda_key,
    b.embedding
from {{ ref('int_producto') }} as p
inner join {{ ref('int_texto_er_tienda') }} as x
    on x.producto_key = p.producto_key
left join {{ ref('emb_texto') }} as b
    on b.texto_hash = x.hash_texto
