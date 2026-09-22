-- Recall del prefiltro por marca (ALD-83) contra el ground truth del
-- crosswalk de aportadores. El prefiltro acotaria producto_candidato_sanfer
-- a las filas de dim_producto cuya descripcion menciona alguna marca de
-- dim_ndf (recorte Sanfer, ver 07_denominador_alcanzable_sanfer.sql). Su
-- valor es precision (evitar que la busqueda vectorial, con una base de solo
-- 1,400 NDF, le asigne el vecino mas cercano a un producto que no es Sanfer),
-- no ahorro. Corrida de referencia 2026-09-22.
--
-- Ground truth: filas de dim_producto con match_method = 'aportadores' cuyo
-- ndf_id cae en el recorte Sanfer -sabemos con certeza que son Sanfer. El
-- recall mide que fraccion de ellas sobrevive el prefiltro (su descripcion
-- matchea AL MENOS UNA de las 158 marcas alcanzables, no necesariamente la
-- suya propia -asi el prefiltro se mide tal cual se usaria en produccion).
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/08_prefiltro_marca_recall.sql
--
-- Decision: SE DESCARTA el prefiltro para la fase Sanfer. Corte 0.95, mejor
-- variante lograda: 0.9351. La causa no es de normalizacion de texto sino
-- estructural: cerca de la mitad del catalogo Sanfer no son marcas
-- comerciales reales sino nombres genericos con un codigo de laboratorio
-- pegado ("TING I.R.", "LORATADINA G.I HOR", "AMPICILINA HORMONA",
-- "FLAGYSTATIN V"), y las tiendas jamas escriben ese codigo -no es un
-- problema de acentos, mayusculas o puntuacion que el aflojado pueda
-- resolver. El diseno no depende del prefiltro: la busqueda vectorial de la
-- fase Sanfer corre sobre el universo completo de dim_producto (240,400
-- filas contra 734 alcanzables, ver ALD-82), mas cara pero viable -y ya
-- cubierta por la compuerta de indice vectorial de ALD-56.

-- Variante 1: patron exacto por marca (identica a 07_denominador...sql).
-- Resultado: 1,384 / 1,510 = 91.66%. Punto de partida, sin aflojar.
--
-- Variante 2: se quita puntuacion (apostrofes, guion, punto, slash) de la
-- marca en vez de reemplazarla por espacio -"KANK-A" -> "KANKA",
-- "TING I.R." -> "TING IR". Resultado: 1384/1510 = 91.66%... en realidad
-- BAJA a 91.66% en la corrida completa contra 93.11% del patron original
-- con espacio: unir palabras que la tienda SI escribe separadas por espacio
-- ("SOME WORD") rompe mas matches de los que arregla. Se descarta esta
-- tecnica -ver el detalle en el comentario del issue.
--
-- Variante 3 (adoptada como mejor intento): prefijos de 4+ caracteres -cada
-- token de 4 o mas letras se compara como prefijo (`TOKEN[A-Z0-9]*`, sin
-- limite de palabra al final), asi "AMARILL" (truncado en el catalogo)
-- matchea "AMARILLO" en la descripcion real. Resultado: 1,412/1,510 =
-- 93.51%. Mejora marginal (+0.4pp) y sigue bajo el corte.

WITH marcas_sanfer AS (
    SELECT DISTINCT producto
    FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
    WHERE UPPER(laboratorio) = 'SANFER'
),

marcas_tokens AS (
    SELECT
        producto,
        SPLIT(
            TRIM(REGEXP_REPLACE(UPPER(producto), r'[^A-Z0-9]+', ' ')),
            ' '
        ) AS lista_tokens
    FROM marcas_sanfer
),

-- Patron con prefijos de 4+ caracteres (variante 3, la adoptada para medir).
marcas_patron AS (
    SELECT
        producto,
        CONCAT(
            r'\b',
            ARRAY_TO_STRING(
                ARRAY(
                    SELECT
                        IF(LENGTH(t) >= 4, CONCAT(t, r'[A-Z0-9]*'), t)
                    FROM UNNEST(lista_tokens) AS t
                ),
                r'\s+'
            ),
            r'\b'
        ) AS patron
    FROM marcas_tokens
),

ground_truth AS (
    SELECT p.producto_key, p.tienda_key, p.descripcion
    FROM `scenic-firefly-473823-f7.precios_gold.dim_producto` AS p
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n
        ON n.ndf_id = p.ndf_id
    WHERE p.match_method = 'aportadores'
        AND UPPER(n.laboratorio) = 'SANFER'
),

evaluado AS (
    SELECT
        gt.producto_key,
        gt.tienda_key,
        (
            SELECT LOGICAL_OR(REGEXP_CONTAINS(gt.descripcion, mp.patron))
            FROM marcas_patron AS mp
        ) AS sobrevive
    FROM ground_truth AS gt
)

-- Recall global. Resultado: 1,412 / 1,510 = 93.51% -bajo el corte de 0.95.
SELECT
    COUNT(*) AS n_ground_truth,
    COUNTIF(sobrevive) AS n_sobrevive,
    ROUND(COUNTIF(sobrevive) / COUNT(*), 4) * 100 AS recall_pct
FROM evaluado;

-- Recall por tienda. Repite el mismo patron y ground truth -una consulta
-- aparte porque el alcance de un WITH en BigQuery no cruza el `;` de la
-- consulta anterior. Confirma la sospecha del issue: hay tiendas que
-- escriben la marca de forma consistentemente distinta. gi (76.92%),
-- aurrera (85.71%) y walmart (86.36%) muy por debajo del resto
-- (benavides 96.53%, sanpablo 96.43%) -mismo patron de calidad de texto
-- dispar entre tiendas que ya aparece en otras partes del modelo.
WITH marcas_sanfer AS (
    SELECT DISTINCT producto
    FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
    WHERE UPPER(laboratorio) = 'SANFER'
),

marcas_tokens AS (
    SELECT
        producto,
        SPLIT(
            TRIM(REGEXP_REPLACE(UPPER(producto), r'[^A-Z0-9]+', ' ')),
            ' '
        ) AS lista_tokens
    FROM marcas_sanfer
),

marcas_patron AS (
    SELECT
        producto,
        CONCAT(
            r'\b',
            ARRAY_TO_STRING(
                ARRAY(
                    SELECT
                        IF(LENGTH(t) >= 4, CONCAT(t, r'[A-Z0-9]*'), t)
                    FROM UNNEST(lista_tokens) AS t
                ),
                r'\s+'
            ),
            r'\b'
        ) AS patron
    FROM marcas_tokens
),

ground_truth AS (
    SELECT p.producto_key, p.tienda_key, p.descripcion
    FROM `scenic-firefly-473823-f7.precios_gold.dim_producto` AS p
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n
        ON n.ndf_id = p.ndf_id
    WHERE p.match_method = 'aportadores'
        AND UPPER(n.laboratorio) = 'SANFER'
),

evaluado AS (
    SELECT
        gt.producto_key,
        gt.tienda_key,
        (
            SELECT LOGICAL_OR(REGEXP_CONTAINS(gt.descripcion, mp.patron))
            FROM marcas_patron AS mp
        ) AS sobrevive
    FROM ground_truth AS gt
)

SELECT
    dim_tienda.tienda_slug,
    COUNT(*) AS n_ground_truth,
    COUNTIF(evaluado.sobrevive) AS n_sobrevive,
    ROUND(COUNTIF(evaluado.sobrevive) / COUNT(*), 4) * 100 AS recall_pct
FROM evaluado
INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS dim_tienda
    ON dim_tienda.tienda_key = evaluado.tienda_key
GROUP BY dim_tienda.tienda_slug
ORDER BY recall_pct ASC;
