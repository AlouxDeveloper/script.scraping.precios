{#
    Falla si algún producto de `dim_producto` no tiene vector vigente en
    `emb_producto`: que falte la fila o que su `texto_hash` no sea el del
    texto actual (ALD-99). Es la señal de que el banco `emb_texto` quedó a
    medias -se llena por lotes de `lote_embeddings`- y hay que volver a
    correr `dbt run --select emb_texto emb_producto` antes de buscar.
    Compara llaves y no busca embeddings nulos: BigQuery guarda un ARRAY
    NULL como arreglo vacío, así que un `not_null` nunca fallaría.
#}
select
    dim_producto.producto_key,
    texto.hash_texto,
    emb_producto.texto_hash as texto_hash_emb
from {{ ref('dim_producto') }} as dim_producto
inner join {{ ref('int_texto_er_tienda') }} as texto
    on texto.producto_key = dim_producto.producto_key
left join {{ ref('emb_producto') }} as emb_producto
    on emb_producto.producto_key = dim_producto.producto_key
where emb_producto.texto_hash is distinct from texto.hash_texto
