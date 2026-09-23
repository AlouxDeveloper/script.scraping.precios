-- Reporte de cierre de la fase catalogo completo (ALD-90): las dos
-- coberturas de la relacion N:1 (por NDF y por producto), el desglose por
-- tienda y una verificacion cruzada gratis entre aportadores y vectorial.
-- Corrida de referencia 2026-09-22, sobre rev_er_cobertura_ndf/producto y
-- el int_match_ndf ya recalibrado (ALD-89) y reapuntado al catalogo
-- completo (ALD-90).
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/17_cobertura_catalogo.sql

-- Paso 1: cobertura por NDF, total y partida por alcanzabilidad
-- (16_denominador_alcanzable_catalogo.sql). Resultado: 23,220/180,914
-- (12.83%) con match -22,542 aportadores, 678 vectorial neto (no ya
-- cubierto por aportadores)-. Partido: alcanzable 19,783/114,173 (17.33%),
-- no observado 3,437/66,741 (5.15% -no deberia ser posible en teoria si
-- "alcanzable" fuera un superconjunto estricto de "tiene match", pero
-- aportadores resuelve por sku, no por texto: un ndf_id puede tener match
-- real sin que su marca aparezca literal en ninguna descripcion. La
-- alcanzabilidad es un proxy de texto, no la verdad).
SELECT
    'total' AS corte, COUNT(*) AS n_ndf, COUNTIF(tiene_match) AS n_con_match,
    COUNTIF(metodo = 'aportadores') AS n_aportadores,
    COUNTIF(metodo = 'vectorial') AS n_vectorial,
    ROUND(SAFE_DIVIDE(COUNTIF(tiene_match), COUNT(*)), 4) AS cobertura_pct
FROM `scenic-firefly-473823-f7.precios_ml.rev_er_cobertura_ndf`
UNION ALL
SELECT
    CAST(a.alcanzable AS STRING),
    COUNT(*), COUNTIF(r.tiene_match),
    COUNTIF(r.metodo = 'aportadores'), COUNTIF(r.metodo = 'vectorial'),
    ROUND(SAFE_DIVIDE(COUNTIF(r.tiene_match), COUNT(*)), 4)
FROM `scenic-firefly-473823-f7.precios_ml.rev_er_cobertura_ndf` AS r
INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS n ON n.ndf_id = r.ndf_id
LEFT JOIN `scenic-firefly-473823-f7.precios_ml.rev_ndf_alcanzabilidad_catalogo` AS a
    ON a.producto = n.producto
GROUP BY a.alcanzable;

-- Paso 2: cobertura por producto, total. Resultado: 66,163/240,400
-- (27.52%) -61,085 aportadores (linea base sin cambios) + 5,078 vectorial
-- neto-, contra 25.41% de linea base (solo aportadores): +2.12pp.
SELECT
    COUNT(*) AS n_producto, COUNTIF(tiene_match) AS n_con_match,
    COUNTIF(metodo = 'aportadores') AS n_aportadores,
    COUNTIF(metodo = 'vectorial') AS n_vectorial,
    ROUND(SAFE_DIVIDE(COUNTIF(tiene_match), COUNT(*)), 4) AS cobertura_pct
FROM `scenic-firefly-473823-f7.precios_ml.rev_er_cobertura_producto`;

-- Paso 3: desglose por tienda. Resultado e interpretacion en el cierre de
-- ALD-90: la cobertura de HOY la domina aportadores (el crosswalk de
-- Knobloch), no vectorial -el patron "farmacia pura mejor que
-- supermercado" que anticipaba el issue no se sostiene limpio (chedraui,
-- heb, comer -supermercados- superan 90%; walmart, aurrera -tambien
-- supermercados- no llegan a 6%): lo que separa a las tiendas es si su
-- SKU coincidio bien con el aportador (0-35% segun tienda, documentado
-- desde antes de esta fase), no si venden medicamentos o abarrotes.
SELECT
    t.tienda_slug,
    COUNT(*) AS n_producto,
    COUNTIF(r.tiene_match) AS n_con_match,
    COUNTIF(r.metodo = 'aportadores') AS n_aportadores,
    COUNTIF(r.metodo = 'vectorial') AS n_vectorial,
    ROUND(SAFE_DIVIDE(COUNTIF(r.tiene_match), COUNT(*)), 4) AS cobertura_pct
FROM `scenic-firefly-473823-f7.precios_ml.rev_er_cobertura_producto` AS r
INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS t ON t.tienda_key = r.tienda_key
GROUP BY t.tienda_slug
ORDER BY cobertura_pct DESC;

-- Paso 4: verificacion cruzada gratis. De los producto_key donde
-- aportadores YA tenia un ndf_id confirmado Y el vectorial, corriendo a
-- ciegas sobre el mismo producto, tambien llego a decision='vectorial'
-- (confianza alta) -no se le da prioridad a aportadores para esta
-- comparacion, se mira que responden los dos por separado-: coinciden
-- 6,184/6,443 (95.98%). Es una confirmacion independiente, con datos de
-- produccion reales y fuera del split de calibracion, de la precision
-- ~0.95-0.96 medida en ALD-89.
SELECT
    COUNTIF(dp.ndf_id = m.ndf_id) AS n_de_acuerdo,
    COUNTIF(dp.ndf_id != m.ndf_id) AS n_en_desacuerdo,
    COUNT(*) AS n_overlap,
    ROUND(SAFE_DIVIDE(COUNTIF(dp.ndf_id = m.ndf_id), COUNT(*)), 4) AS tasa_acuerdo
FROM `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dp
INNER JOIN `scenic-firefly-473823-f7.precios_ml.int_match_ndf` AS m
    ON m.producto_key = dp.producto_key
WHERE dp.match_method = 'aportadores' AND m.decision = 'vectorial';
