-- Indice vectorial real sobre emb_producto (ALD-71). El gate de ALD-56
-- (05_compuerta_indice_vectorial.sql) ya confirmo que TREE_AH esta
-- disponible on-demand; esto es el indice de produccion, no un ensayo.
--
-- Va de este lado (producto, ~240,400 vectores, ~1.4 GB) y no del lado NDF
-- recortado a Sanfer (8.6 MB, bajo el minimo de 10 MB que exige TREE_AH).
-- STORING incluye tienda_key a proposito: permite rankear por
-- (ndf_id, tienda_key) sin volver a la tabla base -el ranking por tienda es
-- el que mide cobertura.
--
-- Se corre a mano, una vez, despues de `dbt run --select emb_producto`:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/12_indice_emb_producto.sql
--
-- La construccion es asincrona: el DDL solo la registra. Pollear con la
-- query de status hasta index_status = 'ACTIVE' y coverage_percentage = 100.

CREATE OR REPLACE VECTOR INDEX emb_producto_idx
ON `scenic-firefly-473823-f7.precios_ml.emb_producto`(embedding)
STORING (producto_key, tienda_key)
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
    last_refresh_time
FROM `scenic-firefly-473823-f7.precios_ml`.INFORMATION_SCHEMA.VECTOR_INDEXES
WHERE index_name = 'emb_producto_idx';
