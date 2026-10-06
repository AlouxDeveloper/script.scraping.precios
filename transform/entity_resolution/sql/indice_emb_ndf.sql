-- Indice vectorial real sobre emb_ndf (ALD-70), la base de la busqueda
-- producto->NDF. Es el unico indice vectorial: el de emb_producto servia a
-- la busqueda NDF->producto de la fase Sanfer y se quito en ALD-99.
-- TREE_AH y no IVF: el lote real de consulta
-- (producto->NDF en la fase catalogo completo) trae cientos de miles de
-- vectores de golpe, el caso que Google documenta para TreeAH; IVF esta
-- pensado para lotes chicos y para afinar con num_lists, que no aplica
-- aqui. TreeAH soporta hasta 200M filas; el catalogo tiene 180,914.
--
-- Va el catalogo completo (180,914, ~1.1 GB), no el recorte Sanfer
-- (~1,400, 8.6 MB) -bajo el minimo de 10 MB que exige TREE_AH, el indice
-- se deshabilitaria solo (BASE_TABLE_TOO_SMALL).
--
-- Desde ALD-99 ya no es un paso manual: el post_hook de `emb_ndf`
-- (macros/indice_vectorial.sql) crea el indice con IF NOT EXISTS en cada
-- run. Este script queda como referencia y para forzar una reconstruccion
-- (CREATE OR REPLACE). A mano:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/indice_emb_ndf.sql
--
-- La construccion es asincrona: el DDL solo la registra. Pollear con la
-- query de status hasta index_status = 'ACTIVE' y coverage_percentage = 100
-- antes de medir cualquier tiempo de busqueda -mientras tanto las filas no
-- indexadas se buscan por fuerza bruta (no se pierden resultados, tarda mas).

CREATE OR REPLACE VECTOR INDEX emb_ndf_idx
ON `scenic-firefly-473823-f7.precios_ml.emb_ndf`(embedding)
STORING (ndf_id)
OPTIONS (index_type = 'TREE_AH', distance_type = 'COSINE');

-- Poll de status: correr repetido a mano hasta ACTIVE / coverage 100.
SELECT
    table_name,
    index_name,
    index_status,
    coverage_percentage,
    unindexed_row_count,
    total_logical_bytes,
    total_storage_bytes,
    creation_time,
    last_refresh_time,
    TIMESTAMP_DIFF(last_refresh_time, creation_time, SECOND) AS segundos_construccion
FROM `scenic-firefly-473823-f7.precios_ml`.INFORMATION_SCHEMA.VECTOR_INDEXES
WHERE index_name = 'emb_ndf_idx';

-- Prueba de uso real: 1,000 vectores de producto como consulta (lote real,
-- no fila por fila, ver el hallazgo de ALD-56) contra el catalogo indexado.
-- Confirma que el indice se usa (no BASE_TABLE_TOO_SMALL,
-- ESTIMATED_PERFORMANCE_GAIN_TOO_LOW ni ninguna otra razon) revisando el job
-- despues de correr esta query:
--   bq show --format=prettyjson -j <job_id> | \
--     python3 -c "import json,sys; d=json.load(sys.stdin); \
--     print(d['statistics']['query'].get('vectorSearchStatistics'))"
SELECT query.producto_key, base.ndf_id, distance
FROM VECTOR_SEARCH(
    TABLE `scenic-firefly-473823-f7.precios_ml.emb_ndf`,
    'embedding',
    (
        SELECT producto_key, embedding
        FROM `scenic-firefly-473823-f7.precios_ml.emb_producto`
        LIMIT 1000
    ),
    'embedding',
    top_k => 5,
    distance_type => 'COSINE'
);
