-- Denominador alcanzable del catalogo completo (ALD-90), gemela de
-- 07_denominador_alcanzable_sanfer.sql (ALD-82) pero escalada a 180,914
-- ndf_id / 30,836 marcas -70x el recorte Sanfer. Corrida de referencia
-- 2026-09-22.
--
-- El metodo de ALD-82 (EXISTS + REGEXP_CONTAINS por marca contra las
-- 240,400 descripciones) NO escala: una corrida de prueba sobre un 10% de
-- las marcas ya agoto el limite de CPU on-demand de BigQuery (19,628
-- CPU-segundos contra un tope de 5,100) antes de terminar. Es una busqueda
-- por regex correlacionada, y BigQuery la ejecuta como un nested loop -el
-- costo escala con marcas x descripciones, no con el tamano de ninguna
-- tabla por separado.
--
-- Se reemplaza por un join por igualdad: en vez de preguntar "aparece esta
-- marca en alguna descripcion" marca por marca, se listan TODAS las frases
-- (n-gramas de 1 a 7 palabras, el maximo de palabras que tiene cualquier
-- marca del catalogo) que aparecen en el universo de tienda una sola vez,
-- y se hace JOIN de las marcas normalizadas contra ese vocabulario de
-- frases -hash join, no nested loop-. Mismo resultado exacto que el metodo
-- de ALD-82 (limite de palabra implicito: un n-grama es una secuencia
-- CONTIGUA de tokens, la misma semantica que el patron `\btoken1\s+token2\b`
-- de la version anterior), miles de veces mas barato: ~20s de corrida
-- contra 19,628+ CPU-segundos que no llegaron a terminar.
--
-- Deja dos tablas en precios_ml -no son modelos dbt, mismo patron que
-- ALD-82; se formalizan como rev_ndf_sin_oferta en una fase posterior
-- (ALD-91, milestone "Entity resolution en gold")-:
--   rev_ndf_alcanzabilidad_catalogo  -- una fila por marca, con el flag.
--   rev_ndf_sin_oferta_catalogo      -- una fila por ndf_id sin oferta
--                                        observada, con su marca y contexto.
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/16_denominador_alcanzable_catalogo.sql

CREATE OR REPLACE TABLE `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_catalogo` AS
WITH tokens_desc AS (
    SELECT dp.producto_key, pos, token
    FROM `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dp,
        UNNEST(SPLIT(TRIM(REGEXP_REPLACE(UPPER(dp.descripcion), r'[^A-Z0-9]+', ' ')), ' '))
            AS token WITH OFFSET pos
),

starts AS (
    -- 7: el maximo de palabras entre las marcas de dim_ndf (ver el sweep
    -- de conteo de tokens en el issue). Un n-grama mas largo que cualquier
    -- marca real no sirve para nada, asi que no hay razon para ir mas alla.
    SELECT producto_key, pos, n
    FROM tokens_desc
    CROSS JOIN UNNEST(GENERATE_ARRAY(1, 7)) AS n
),

vocabulario_frases AS (
    SELECT DISTINCT
        STRING_AGG(tokens_desc.token, ' ' ORDER BY tokens_desc.pos) AS frase
    FROM starts
    JOIN tokens_desc
        ON tokens_desc.producto_key = starts.producto_key
        AND tokens_desc.pos BETWEEN starts.pos AND starts.pos + starts.n - 1
    GROUP BY starts.producto_key, starts.pos, starts.n
),

marcas AS (
    SELECT DISTINCT producto
    FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
)

SELECT
    marcas.producto,
    TRIM(REGEXP_REPLACE(UPPER(marcas.producto), r'[^A-Z0-9]+', ' ')) AS marca_norm,
    vocabulario_frases.frase IS NOT NULL AS alcanzable
FROM marcas
LEFT JOIN vocabulario_frases
    ON vocabulario_frases.frase = TRIM(REGEXP_REPLACE(UPPER(marcas.producto), r'[^A-Z0-9]+', ' '));

-- Conteo de marcas.
SELECT alcanzable, COUNT(*) AS n_marcas
FROM `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_catalogo`
GROUP BY alcanzable;

-- Denominador partido a nivel ndf_id -una marca puede cubrir varios ndf_id
-- (presentaciones distintas de la misma marca).
SELECT m.alcanzable, COUNT(DISTINCT n.ndf_id) AS n_ndf_id
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n
INNER JOIN `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_catalogo` AS m
    ON m.producto = n.producto
GROUP BY m.alcanzable;

-- Entregable: lista de ndf_id sin oferta observada, con su marca y
-- contexto (presentacion, forma, division, laboratorio) para revisar a ojo.
CREATE OR REPLACE TABLE `scenic-firefly-473823-f7.precios_ml.rev_ndf_sin_oferta_catalogo` AS
SELECT
    n.ndf_id,
    n.producto AS marca,
    n.presentacion,
    n.forma_farmaceutica_n3,
    n.division,
    n.laboratorio
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n
INNER JOIN `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_catalogo` AS m
    ON m.producto = n.producto
WHERE m.alcanzable = FALSE
ORDER BY n.producto, n.ndf_id;
