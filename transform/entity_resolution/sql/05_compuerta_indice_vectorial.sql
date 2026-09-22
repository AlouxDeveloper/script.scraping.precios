-- Compuerta del indice vectorial (ALD-56): confirma si `VECTOR_INDEX` TREE_AH
-- esta disponible antes de dimensionar la busqueda del entity resolution.
-- Corrida de referencia el 2026-09-22, sin Vertex (vectores sinteticos).
--
-- Respuesta: SI esta disponible. La documentacion de Google dice que el
-- indice vectorial "no esta disponible en Standard edition" (edition de
-- reserva de slots), pero on-demand -sin reserva, que es como factura este
-- proyecto (INFORMATION_SCHEMA.RESERVATIONS vacio en region-us)- tiene
-- soporte completo, igual que Enterprise/Enterprise Plus. Confirmado en
-- docs.cloud.google.com/bigquery/docs/editions-intro y verificado aqui de
-- forma empirica: el indice se construyo, llego a ACTIVE con 100% de
-- cobertura, y un VECTOR_SEARCH en lote lo uso (`indexUsageMode = FULLY_USED`).
--
-- Se corre a mano, desde la raiz del repo, y se limpia al terminar (ver el
-- DROP TABLE al final; el indice se cae solo con la tabla):
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/05_compuerta_indice_vectorial.sql

-- Paso 0: confirmar que no hay reserva de slots (edition por reserva).
-- Resultado: 0 filas -> el proyecto factura on-demand.
SELECT *
FROM `scenic-firefly-473823-f7.region-us`.INFORMATION_SCHEMA.RESERVATIONS;

-- Paso 1: tabla sintetica, 200,000 filas de ARRAY<FLOAT64> de 768 posiciones.
-- Resultado: 200,000 filas, 1,236,400,000 bytes (~1.18 GB) -muy por encima
-- del minimo de 10 MB que exige TREE_AH.
CREATE OR REPLACE TABLE `scenic-firefly-473823-f7.precios_ml.tmp_ald56_sintetico` AS
SELECT
    GENERATE_UUID() AS id,
    ARRAY(
        SELECT RAND()
        FROM UNNEST(GENERATE_ARRAY(1, 768))
    ) AS embedding
FROM UNNEST(GENERATE_ARRAY(1, 200000));

-- Paso 2: construir el indice. El DDL solo lo registra -la construccion es
-- asincrona, ver paso 3.
CREATE VECTOR INDEX ald56_idx
ON `scenic-firefly-473823-f7.precios_ml.tmp_ald56_sintetico`(embedding)
OPTIONS (
    index_type = 'TREE_AH',
    distance_type = 'COSINE'
);

-- Paso 3: pollear hasta cobertura completa (correr repetido a mano).
-- Resultado: ACTIVE, coverage_percentage = 100, unindexed_row_count = 0.
-- Construccion: de creation_time (20:03:39) a last_refresh_time (20:11:16)
-- = 453 s (~7.5 min) para 200k filas. Tamano del indice:
-- total_storage_bytes = 41,872,105 (~41.9 MB) sobre una tabla de ~1.18 GB.
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
WHERE index_name = 'ald56_idx';

-- Paso 4: probar VECTOR_SEARCH con una sola fila de consulta.
-- Resultado real: indexUsageMode = UNUSED, razon
-- ESTIMATED_PERFORMANCE_GAIN_TOO_LOW -con una sola fila de consulta contra
-- 200k, el optimizador prefiere fuerza bruta: es mas barato que pagar el
-- overhead del indice. No es que el indice no sirva, es que ninguna
-- consulta de una sola fila lo justifica.
SELECT base.id, distance
FROM VECTOR_SEARCH(
    TABLE `scenic-firefly-473823-f7.precios_ml.tmp_ald56_sintetico`,
    'embedding',
    (SELECT ARRAY(SELECT RAND() FROM UNNEST(GENERATE_ARRAY(1, 768))) AS embedding),
    top_k => 5,
    distance_type => 'COSINE'
);

-- Paso 5: probar VECTOR_SEARCH en lote (1,000 vectores de consulta a la vez),
-- que es el patron real del entity resolution (embeddings de producto o de
-- NDF corren en lote, nunca de a uno). Resultado: indexUsageMode =
-- FULLY_USED. El indice si se usa cuando el volumen de la consulta lo
-- justifica.
CREATE OR REPLACE TABLE `scenic-firefly-473823-f7.precios_ml.tmp_ald56_queries` AS
SELECT
    GENERATE_UUID() AS query_id,
    ARRAY(
        SELECT RAND()
        FROM UNNEST(GENERATE_ARRAY(1, 768))
    ) AS embedding
FROM UNNEST(GENERATE_ARRAY(1, 1000));

SELECT query.query_id, base.id, distance
FROM VECTOR_SEARCH(
    TABLE `scenic-firefly-473823-f7.precios_ml.tmp_ald56_sintetico`,
    'embedding',
    TABLE `scenic-firefly-473823-f7.precios_ml.tmp_ald56_queries`,
    'embedding',
    top_k => 5,
    distance_type => 'COSINE'
);

-- Paso 6: limpieza. Borrar la tabla borra el indice con ella.
DROP TABLE `scenic-firefly-473823-f7.precios_ml.tmp_ald56_sintetico`;
DROP TABLE `scenic-firefly-473823-f7.precios_ml.tmp_ald56_queries`;
