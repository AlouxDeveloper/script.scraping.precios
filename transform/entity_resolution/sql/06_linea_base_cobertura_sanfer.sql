-- Linea base de cobertura Sanfer (ALD-81): lo que ya da el crosswalk de
-- aportadores (match_method = 'aportadores'), antes de que exista la pasada
-- por texto. Contra esto se compara la cobertura final de cada fase
-- vectorial. Corrida de referencia 2026-09-22.
--
-- Se corre a mano, desde la raiz del repo, y se re-corre identica al cerrar
-- cada fase del entity resolution:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/06_linea_base_cobertura_sanfer.sql

-- Cobertura global. Resultado: 281 / 1,389 = 20.23%.
SELECT
    COUNT(DISTINCT n.ndf_id) AS ndf_sanfer_total,
    COUNT(DISTINCT p.ndf_id) AS ndf_sanfer_asignados,
    ROUND(COUNT(DISTINCT p.ndf_id) / COUNT(DISTINCT n.ndf_id), 4) * 100
        AS cobertura_pct
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n
LEFT JOIN `scenic-firefly-473823-f7.precios_gold.dim_producto` AS p
    ON p.ndf_id = n.ndf_id
WHERE UPPER(n.laboratorio) = 'SANFER';

-- Desglose por tienda, incluyendo las 19 tiendas aunque su cobertura sea 0
-- -es el dato interesante: dice donde el metodo vectorial tiene que hacer
-- todo el trabajo. Resultado: guadalajara (17.21%, 239) e isseg (16.34%, 227)
-- a la cabeza; soriana, fahorro, alsuper, farmalisto, yza, fesa y similares
-- en 0% -mismo patron de sku sin match que documenta `dim_puente_aportador`.
WITH sanfer AS (
    SELECT ndf_id
    FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
    WHERE UPPER(laboratorio) = 'SANFER'
),

match AS (
    SELECT DISTINCT p.tienda_key, p.ndf_id
    FROM `scenic-firefly-473823-f7.precios_gold.dim_producto` AS p
    INNER JOIN sanfer ON sanfer.ndf_id = p.ndf_id
)

SELECT
    dim_tienda.tienda_slug,
    COUNT(match.ndf_id) AS ndf_sanfer_asignados,
    ROUND(COUNT(match.ndf_id) / (SELECT COUNT(*) FROM sanfer), 4) * 100
        AS cobertura_pct
FROM `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS dim_tienda
LEFT JOIN match
    ON match.tienda_key = dim_tienda.tienda_key
GROUP BY dim_tienda.tienda_slug
ORDER BY ndf_sanfer_asignados DESC;
