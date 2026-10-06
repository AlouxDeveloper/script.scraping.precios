{#
    Gemelo de `assert_emb_producto_cobertura` para el catálogo: falla si
    algún `ndf_id` de `dim_ndf` no tiene vector del texto vigente
    (`variante_ndf`) en `emb_ndf`.
#}
select
    dim_ndf.ndf_id,
    texto.hash_texto,
    emb_ndf.texto_hash as texto_hash_emb
from {{ ref('dim_ndf') }} as dim_ndf
inner join {{ ref('int_texto_er_ndf') }} as texto
    on texto.ndf_id = dim_ndf.ndf_id
left join {{ ref('emb_ndf') }} as emb_ndf
    on emb_ndf.ndf_id = dim_ndf.ndf_id
where emb_ndf.texto_hash is distinct from texto.hash_texto
