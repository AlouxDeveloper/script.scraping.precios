-- Modelo remoto emb_gemini: referencia de BigQuery al endpoint de embeddings
-- de Vertex AI, contra la conexión BigLake `vertex` (02_conexion_vertex.sh).
--
-- AI.GENERATE_EMBEDDING lo usa en cada llamada. La función se llamaba
-- ML.GENERATE_EMBEDDING; se renombró a AI.GENERATE_EMBEDDING, confirmado
-- contra docs.cloud.google.com (no contra memoria ni ejemplos de blog).
--
-- Se corre a mano una sola vez, desde la raíz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/03_modelo_emb_gemini.sql
--
-- output_dimensionality y task_type NO se fijan aquí: son parámetros de la
-- llamada a AI.GENERATE_EMBEDDING (STRUCT), no del modelo. Van en cada query
-- (768 y SEMANTIC_SIMILARITY, ver ALD-55) y entran al hash del banco
-- emb_texto, así que cambiarlos después no corrompe nada: genera una
-- generación de vectores nueva que convive con la anterior.

CREATE OR REPLACE MODEL `scenic-firefly-473823-f7.precios_ml.emb_gemini`
REMOTE WITH CONNECTION `scenic-firefly-473823-f7.US.vertex`
OPTIONS (ENDPOINT = 'gemini-embedding-001');
