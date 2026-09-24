-- Dataset precios_ml: infraestructura del entity resolution vectorial.
--
-- Primero de tres pasos de una sola vez, en este orden: este dataset,
-- luego conexion_vertex.sh y al final modelo_emb_gemini.sql.
--
-- Aloja lo que no es una tabla de negocio: el modelo remoto de embeddings, el
-- banco emb_texto, los vectores del catálogo NDF y el índice vectorial. Va
-- aparte de precios_gold porque gold se reconstruye entero en cada build y los
-- embeddings son llamadas a la API ya pagadas.
--
-- Se corre a mano una sola vez, desde la raíz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/dataset_precios_ml.sql
--
-- La location US es obligatoria: una conexión BigLake y un modelo remoto solo
-- pueden usarse desde un dataset de la misma región, y el resto del proyecto
-- (precios_bronce, precios_silver, precios_gold) ya vive en US.

CREATE SCHEMA IF NOT EXISTS `scenic-firefly-473823-f7.precios_ml`
OPTIONS (
    location = 'US',
    description = 'Entity resolution vectorial: modelo remoto de embeddings, banco emb_texto e indice vectorial del catalogo NDF.'
);
