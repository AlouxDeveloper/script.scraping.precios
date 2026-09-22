-- Denominador alcanzable del recorte Sanfer (ALD-82): separa los ndf_id que
-- SI pueden llegar a tener match (su marca aparece en el universo de tienda)
-- de los que no se vendieron en ninguna de las 19 tiendas o no fueron
-- capturados por el scraping. La meta del proyecto es el 100% del grupo
-- alcanzable, no de los ~1,400 de dim_ndf. Corrida de referencia 2026-09-22.
--
-- Busqueda por token, no por subcadena: cada marca normalizada
-- (mayusculas, puntuacion -> espacio, espacios colapsados) se arma como
-- patron `\btoken1\s+token2...\b` con limite de palabra en ambos extremos,
-- para que una marca corta como "AMAL" no aparezca como falso positivo
-- dentro de otra palabra ("AMALGAMA" no matchea: no hay limite de palabra
-- entre "AMAL" y la "G" que sigue). Las marcas de 4-5 caracteres alcanzables
-- se revisaron a mano contra sus descripciones reales (ver comentario del
-- issue): todas fueron el nombre real del producto en cabeza de la
-- descripcion, no coincidencias espureas.
--
-- Deja dos tablas en precios_ml -no son modelos dbt, son la primera version
-- del entregable; se formaliza como `rev_ndf_sin_oferta` mas adelante, no
-- aqui-:
--   rev_ndf_alcanzabilidad_sanfer  -- una fila por marca (`producto`), con
--                                      el flag alcanzable.
--   rev_ndf_sin_oferta_sanfer      -- una fila por ndf_id sin oferta
--                                      observada, con su marca y contexto,
--                                      para revisar a ojo.
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/07_denominador_alcanzable_sanfer.sql

CREATE OR REPLACE TABLE `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_sanfer` AS
WITH marcas_sanfer AS (
    SELECT DISTINCT producto
    FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
    WHERE UPPER(laboratorio) = 'SANFER'
),

marcas_patron AS (
    SELECT
        producto,
        TRIM(REGEXP_REPLACE(UPPER(producto), r'[^A-Z0-9]+', ' ')) AS marca_norm,
        CONCAT(
            r'\b',
            ARRAY_TO_STRING(
                SPLIT(TRIM(REGEXP_REPLACE(UPPER(producto), r'[^A-Z0-9]+', ' ')), ' '),
                r'\s+'
            ),
            r'\b'
        ) AS patron
    FROM marcas_sanfer
)

SELECT
    producto,
    marca_norm,
    patron,
    EXISTS(
        SELECT 1
        FROM `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dp
        WHERE REGEXP_CONTAINS(dp.descripcion, patron)
    ) AS alcanzable
FROM marcas_patron;

-- Conteo de marcas. Resultado: 158 alcanzables / 282 no observadas (440 total).
SELECT alcanzable, COUNT(*) AS n_marcas
FROM `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_sanfer`
GROUP BY alcanzable;

-- Denominador partido a nivel ndf_id. Resultado: 734 alcanzables / 655 no
-- observados (1,389 total) -una marca puede cubrir varios ndf_id
-- (presentaciones distintas de la misma marca).
SELECT m.alcanzable, COUNT(DISTINCT n.ndf_id) AS n_ndf_id
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n
INNER JOIN `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_sanfer` AS m
    ON m.producto = n.producto
WHERE UPPER(n.laboratorio) = 'SANFER'
GROUP BY m.alcanzable;

-- Entregable: lista de ndf_id sin oferta observada, con su marca y contexto
-- (presentacion, forma, division) para revisar a ojo.
CREATE OR REPLACE TABLE `scenic-firefly-473823-f7.precios_ml.rev_ndf_sin_oferta_sanfer` AS
SELECT
    n.ndf_id,
    n.producto AS marca,
    n.presentacion,
    n.forma_farmaceutica_n3,
    n.division
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n
INNER JOIN `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_sanfer` AS m
    ON m.producto = n.producto
WHERE UPPER(n.laboratorio) = 'SANFER'
    AND m.alcanzable = FALSE
ORDER BY n.producto, n.ndf_id;
