-- Conteos del recorte Sanfer (ALD-80): dimensiona el banco de embeddings antes
-- de tocar Vertex. Corridas de referencia contra `precios_gold`, resultado
-- fijado el 2026-09-22 (el catálogo NDF y el histórico de tienda son snapshots
-- que se regeneran, así que estos números pueden moverse en corridas futuras).
--
-- Se corre a mano, desde la raíz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/04_conteos_recorte_sanfer.sql

-- Lado catalogo -------------------------------------------------------------

-- ndf_id con laboratorio = SANFER. Resultado: 1,389 (orden esperado ~1,400).
SELECT COUNT(*) AS n_ndf_id
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
WHERE upper(laboratorio) = 'SANFER';

-- Marcas comerciales distintas (`producto`) dentro del recorte. Resultado: 440.
-- Insumo del prefiltro por marca antes de correr embeddings.
SELECT COUNT(DISTINCT producto) AS n_marcas
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
WHERE upper(laboratorio) = 'SANFER';

-- Distribucion por division. Resultado: FARMA 1,299 / NO FARMA 90.
SELECT division, COUNT(*) AS n_ndf_id
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
WHERE upper(laboratorio) = 'SANFER'
GROUP BY division
ORDER BY n_ndf_id DESC;

-- Distribucion por forma_farmaceutica_n3. Larga cola; top 3: ORAL S.ORD.TABLETAS
-- (378), ORAL S.ORD.CAPSULAS (157), SIN FF (90, son los NO FARMA sin forma).
SELECT forma_farmaceutica_n3, COUNT(*) AS n_ndf_id
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
WHERE upper(laboratorio) = 'SANFER'
GROUP BY forma_farmaceutica_n3
ORDER BY n_ndf_id DESC;

-- Confirma por que el filtro va por laboratorio y no por corporacion:
-- SANFER CORP. agrupa 5 laboratorios (HORMONA, MAVI, MORE PHARMACORP, SANFER,
-- VITALIS S.A.). Filtrar por corporacion metería 4 laboratorios ajenos.
SELECT DISTINCT laboratorio
FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
WHERE corporacion IN (
    SELECT corporacion
    FROM `scenic-firefly-473823-f7.precios_gold.dim_ndf`
    WHERE upper(laboratorio) = 'SANFER'
);

-- Lado tienda -----------------------------------------------------------------

-- Conteo real de dim_producto. Resultado: 240,400 -confirma la cifra de
-- dim_producto.sql y de 61,085 de 240,400 en match_aportador; la que estaba
-- mal era el "~160 mil" de _dim_producto.yml, ya corregido ahí.
SELECT COUNT(*) AS n_filas
FROM `scenic-firefly-473823-f7.precios_gold.dim_producto`;

-- Desglose por tienda. Confirma el desbalance: walmart (68,745) y aurrera
-- (66,650) dominan; chedraui (4,441), comer (6,131) y heb (5,001) son las
-- mas chicas del rango 4-6k citado en el issue.
SELECT dim_tienda.tienda_slug, COUNT(*) AS n_filas
FROM `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dim_producto
INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS dim_tienda
    ON dim_producto.tienda_key = dim_tienda.tienda_key
GROUP BY dim_tienda.tienda_slug
ORDER BY n_filas DESC;
