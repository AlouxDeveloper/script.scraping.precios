-- Recalibracion de tau_alto, tau_bajo y delta_min sobre el universo completo
-- (ALD-89), gemela de 14_calibracion_umbrales_sanfer.sql pero sobre
-- int_candidatos_producto (ALD-88) en vez de int_candidatos_ndf. Mismo split
-- de calibracion (ALD-65), mismas guardas (macros/guarda_magnitudes.sql).
-- Corrida de referencia 2026-09-22. Resultado y decision final anotados en
-- el issue de Linear; este archivo deja las consultas reproducibles.
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/15_calibracion_umbrales_catalogo.sql

-- Paso 1a: sweep de tau_alto por bucket, SOBRE EL UNIVERSO MIXTO (cualquier
-- laboratorio verdadero). Resultado: la precision NUNCA cruza 0.95 -techo
-- real 0.923 en bucket A (umbral 0.0, n=65, ruido de muestra), decreciente
-- monotono despues. Confirma la advertencia del issue: con 180,914
-- candidatos, el vecino mas cercano de un producto NO FARMA suele ser un
-- NDF real, no un artefacto, y eso arrastra la precision agregada por
-- debajo del objetivo sin importar el umbral.
WITH bucket_tienda AS (
    SELECT tienda_slug,
        CASE
            WHEN tienda_slug IN (
                'gi', 'klyns', 'isseg', 'aurrera', 'heb', 'farmatodo',
                'guadalajara', 'benavides', 'walmart'
            ) THEN 'A'
            ELSE 'B'
        END AS bucket
    FROM `scenic-firefly-473823-f7.precios_gold.dim_tienda`
),

universo AS (
    SELECT
        split.producto_key,
        bucket_tienda.bucket,
        dp.ndf_id AS ndf_id_verdadero,
        UPPER(dn.division) = 'NO FARMA' AS es_no_farma
    FROM `scenic-firefly-473823-f7.precios_ml.producto_split_aportadores` AS split
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dp
        ON dp.producto_key = split.producto_key
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS dn
        ON dn.ndf_id = dp.ndf_id
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS dim_tienda
        ON dim_tienda.tienda_key = split.tienda_key
    INNER JOIN bucket_tienda
        ON bucket_tienda.tienda_slug = dim_tienda.tienda_slug
    WHERE split.split = 'calibracion'
),

candidato_top AS (
    SELECT
        producto_key,
        ndf_id AS ndf_id_candidato,
        distancia,
        margen,
        es_reciproco
        AND (atributos_producto.dosis_mg IS NULL OR atributos_ndf.dosis_mg IS NULL
             OR atributos_producto.dosis_mg = atributos_ndf.dosis_mg)
        AND (atributos_producto.volumen_ml IS NULL OR atributos_ndf.volumen_ml IS NULL
             OR atributos_producto.volumen_ml = atributos_ndf.volumen_ml)
        AND (atributos_producto.masa_g IS NULL OR atributos_ndf.masa_g IS NULL
             OR atributos_producto.masa_g = atributos_ndf.masa_g)
        AND (atributos_producto.piezas IS NULL OR atributos_ndf.piezas IS NULL
             OR atributos_producto.piezas = atributos_ndf.piezas) AS pasa_guardas
    FROM `scenic-firefly-473823-f7.precios_ml.int_candidatos_producto`
    WHERE rank_desde_producto = 1
),

universo_top AS (
    SELECT
        universo.bucket,
        universo.es_no_farma,
        (candidato_top.ndf_id_candidato IS NOT NULL AND candidato_top.pasa_guardas)
            AS candidato_confiable,
        candidato_top.distancia,
        candidato_top.ndf_id_candidato = universo.ndf_id_verdadero AS top1_correcto
    FROM universo
    LEFT JOIN candidato_top USING (producto_key)
),

umbrales AS (
    SELECT ROUND(umbral, 3) AS umbral
    FROM UNNEST(GENERATE_ARRAY(0.0, 0.05, 0.002)) AS umbral
)

SELECT
    universo_top.bucket,
    umbrales.umbral AS tau_alto_candidato,
    COUNT(*) AS n_total,
    COUNTIF(universo_top.candidato_confiable AND universo_top.distancia <= umbrales.umbral)
        AS n_aceptado,
    SAFE_DIVIDE(
        COUNTIF(
            universo_top.candidato_confiable
            AND universo_top.distancia <= umbrales.umbral AND universo_top.top1_correcto
        ),
        COUNTIF(
            universo_top.candidato_confiable
            AND universo_top.distancia <= umbrales.umbral
        )
    ) AS precision
FROM universo_top
CROSS JOIN umbrales
GROUP BY universo_top.bucket, umbrales.umbral
ORDER BY universo_top.bucket, umbrales.umbral;

-- Paso 1b: mismo sweep, restringido a la verdad FARMA (NOT es_no_farma).
-- Aqui si cruza 0.95: bucket A en 0.022 (precision 0.9619, n=2,624
-- aceptados; 0.024 ya cae a 0.9494, se toma el valor conservador). Bucket B
-- en 0.018 (precision 0.9333, n=30 -muestra chica, no cruza 0.95 con
-- confianza, avisado y no ignorado, mismo patron que Sanfer bucket B).
WITH bucket_tienda AS (
    SELECT tienda_slug,
        CASE
            WHEN tienda_slug IN (
                'gi', 'klyns', 'isseg', 'aurrera', 'heb', 'farmatodo',
                'guadalajara', 'benavides', 'walmart'
            ) THEN 'A'
            ELSE 'B'
        END AS bucket
    FROM `scenic-firefly-473823-f7.precios_gold.dim_tienda`
),

universo AS (
    SELECT
        split.producto_key,
        bucket_tienda.bucket,
        dp.ndf_id AS ndf_id_verdadero,
        UPPER(dn.division) = 'NO FARMA' AS es_no_farma
    FROM `scenic-firefly-473823-f7.precios_ml.producto_split_aportadores` AS split
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dp
        ON dp.producto_key = split.producto_key
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS dn
        ON dn.ndf_id = dp.ndf_id
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS dim_tienda
        ON dim_tienda.tienda_key = split.tienda_key
    INNER JOIN bucket_tienda
        ON bucket_tienda.tienda_slug = dim_tienda.tienda_slug
    WHERE split.split = 'calibracion'
),

candidato_top AS (
    SELECT
        producto_key,
        ndf_id AS ndf_id_candidato,
        distancia,
        margen,
        es_reciproco
        AND (atributos_producto.dosis_mg IS NULL OR atributos_ndf.dosis_mg IS NULL
             OR atributos_producto.dosis_mg = atributos_ndf.dosis_mg)
        AND (atributos_producto.volumen_ml IS NULL OR atributos_ndf.volumen_ml IS NULL
             OR atributos_producto.volumen_ml = atributos_ndf.volumen_ml)
        AND (atributos_producto.masa_g IS NULL OR atributos_ndf.masa_g IS NULL
             OR atributos_producto.masa_g = atributos_ndf.masa_g)
        AND (atributos_producto.piezas IS NULL OR atributos_ndf.piezas IS NULL
             OR atributos_producto.piezas = atributos_ndf.piezas) AS pasa_guardas
    FROM `scenic-firefly-473823-f7.precios_ml.int_candidatos_producto`
    WHERE rank_desde_producto = 1
),

universo_top AS (
    SELECT
        universo.bucket,
        (candidato_top.ndf_id_candidato IS NOT NULL AND candidato_top.pasa_guardas)
            AS candidato_confiable,
        candidato_top.distancia,
        candidato_top.ndf_id_candidato = universo.ndf_id_verdadero AS top1_correcto
    FROM universo
    LEFT JOIN candidato_top USING (producto_key)
    WHERE NOT universo.es_no_farma
),

umbrales AS (
    SELECT ROUND(umbral, 3) AS umbral
    FROM UNNEST(GENERATE_ARRAY(0.0, 0.05, 0.002)) AS umbral
)

SELECT
    universo_top.bucket,
    umbrales.umbral AS tau_alto_candidato,
    COUNT(*) AS n_farma,
    COUNTIF(universo_top.candidato_confiable AND universo_top.distancia <= umbrales.umbral)
        AS n_aceptado,
    SAFE_DIVIDE(
        COUNTIF(
            universo_top.candidato_confiable
            AND universo_top.distancia <= umbrales.umbral AND universo_top.top1_correcto
        ),
        COUNTIF(
            universo_top.candidato_confiable
            AND universo_top.distancia <= umbrales.umbral
        )
    ) AS precision
FROM universo_top
CROSS JOIN umbrales
GROUP BY universo_top.bucket, umbrales.umbral
ORDER BY universo_top.bucket, umbrales.umbral;

-- Paso 2: distribucion de margen entre aceptados por distancia (tau_alto
-- elegido: A=0.022, B=0.018), verdad FARMA, separado por si el top1 fue
-- correcto. Resultado: bucket A, aciertos (n=2,524) margen mediano 0.0264
-- contra 0.0062 de los errores (n=100) -mas de 4x, la separacion se
-- mantiene igual de limpia que en Sanfer pese a la mayor densidad.
WITH bucket_tienda AS (
    SELECT tienda_slug,
        CASE
            WHEN tienda_slug IN (
                'gi', 'klyns', 'isseg', 'aurrera', 'heb', 'farmatodo',
                'guadalajara', 'benavides', 'walmart'
            ) THEN 'A'
            ELSE 'B'
        END AS bucket
    FROM `scenic-firefly-473823-f7.precios_gold.dim_tienda`
),

universo AS (
    SELECT
        split.producto_key,
        bucket_tienda.bucket,
        dp.ndf_id AS ndf_id_verdadero,
        UPPER(dn.division) = 'NO FARMA' AS es_no_farma
    FROM `scenic-firefly-473823-f7.precios_ml.producto_split_aportadores` AS split
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dp
        ON dp.producto_key = split.producto_key
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS dn
        ON dn.ndf_id = dp.ndf_id
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS dim_tienda
        ON dim_tienda.tienda_key = split.tienda_key
    INNER JOIN bucket_tienda
        ON bucket_tienda.tienda_slug = dim_tienda.tienda_slug
    WHERE split.split = 'calibracion'
),

candidato_top AS (
    SELECT
        producto_key,
        ndf_id AS ndf_id_candidato,
        distancia,
        margen,
        es_reciproco
        AND (atributos_producto.dosis_mg IS NULL OR atributos_ndf.dosis_mg IS NULL
             OR atributos_producto.dosis_mg = atributos_ndf.dosis_mg)
        AND (atributos_producto.volumen_ml IS NULL OR atributos_ndf.volumen_ml IS NULL
             OR atributos_producto.volumen_ml = atributos_ndf.volumen_ml)
        AND (atributos_producto.masa_g IS NULL OR atributos_ndf.masa_g IS NULL
             OR atributos_producto.masa_g = atributos_ndf.masa_g)
        AND (atributos_producto.piezas IS NULL OR atributos_ndf.piezas IS NULL
             OR atributos_producto.piezas = atributos_ndf.piezas) AS pasa_guardas
    FROM `scenic-firefly-473823-f7.precios_ml.int_candidatos_producto`
    WHERE rank_desde_producto = 1
),

aceptados_por_distancia AS (
    SELECT
        universo.bucket,
        candidato_top.margen,
        candidato_top.ndf_id_candidato = universo.ndf_id_verdadero AS top1_correcto
    FROM universo
    INNER JOIN candidato_top USING (producto_key)
    WHERE NOT universo.es_no_farma
        AND candidato_top.ndf_id_candidato IS NOT NULL
        AND candidato_top.pasa_guardas
        AND (
            (universo.bucket = 'A' AND candidato_top.distancia <= 0.022)
            OR (universo.bucket = 'B' AND candidato_top.distancia <= 0.018)
        )
)

SELECT
    bucket,
    top1_correcto,
    COUNT(*) AS n,
    ROUND(AVG(margen), 5) AS margen_prom,
    APPROX_QUANTILES(margen, 4)[OFFSET(2)] AS margen_mediana
FROM aceptados_por_distancia
GROUP BY bucket, top1_correcto
ORDER BY bucket, top1_correcto;

-- Paso 3: sweep de delta_min GLOBAL (pooled A+B), verdad FARMA, sobre esos
-- mismos aceptados por distancia. Resultado: 0.008 -el mismo valor de
-- Sanfer- sigue siendo el punto de rendimientos decrecientes: atrapa 56%
-- de los "confiados pero equivocados" (57 de 102) al costo de solo 4.0% de
-- los aciertos reales (101 de 2,552) -mejor relacion que el 10.7% de
-- Sanfer, no peor-; subir a 0.01 solo atrapa 7 mas al costo de 78 aciertos
-- adicionales, dominado. delta_min AGUANTA sin cambios.
WITH bucket_tienda AS (
    SELECT tienda_slug,
        CASE
            WHEN tienda_slug IN (
                'gi', 'klyns', 'isseg', 'aurrera', 'heb', 'farmatodo',
                'guadalajara', 'benavides', 'walmart'
            ) THEN 'A'
            ELSE 'B'
        END AS bucket
    FROM `scenic-firefly-473823-f7.precios_gold.dim_tienda`
),

universo AS (
    SELECT
        split.producto_key,
        bucket_tienda.bucket,
        dp.ndf_id AS ndf_id_verdadero,
        UPPER(dn.division) = 'NO FARMA' AS es_no_farma
    FROM `scenic-firefly-473823-f7.precios_ml.producto_split_aportadores` AS split
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_producto` AS dp
        ON dp.producto_key = split.producto_key
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_ndf` AS dn
        ON dn.ndf_id = dp.ndf_id
    INNER JOIN `scenic-firefly-473823-f7.precios_gold.dim_tienda` AS dim_tienda
        ON dim_tienda.tienda_key = split.tienda_key
    INNER JOIN bucket_tienda
        ON bucket_tienda.tienda_slug = dim_tienda.tienda_slug
    WHERE split.split = 'calibracion'
),

candidato_top AS (
    SELECT
        producto_key,
        ndf_id AS ndf_id_candidato,
        distancia,
        margen,
        es_reciproco
        AND (atributos_producto.dosis_mg IS NULL OR atributos_ndf.dosis_mg IS NULL
             OR atributos_producto.dosis_mg = atributos_ndf.dosis_mg)
        AND (atributos_producto.volumen_ml IS NULL OR atributos_ndf.volumen_ml IS NULL
             OR atributos_producto.volumen_ml = atributos_ndf.volumen_ml)
        AND (atributos_producto.masa_g IS NULL OR atributos_ndf.masa_g IS NULL
             OR atributos_producto.masa_g = atributos_ndf.masa_g)
        AND (atributos_producto.piezas IS NULL OR atributos_ndf.piezas IS NULL
             OR atributos_producto.piezas = atributos_ndf.piezas) AS pasa_guardas
    FROM `scenic-firefly-473823-f7.precios_ml.int_candidatos_producto`
    WHERE rank_desde_producto = 1
),

aceptados_por_distancia AS (
    SELECT
        candidato_top.margen,
        candidato_top.ndf_id_candidato = universo.ndf_id_verdadero AS top1_correcto
    FROM universo
    INNER JOIN candidato_top USING (producto_key)
    WHERE NOT universo.es_no_farma
        AND candidato_top.ndf_id_candidato IS NOT NULL
        AND candidato_top.pasa_guardas
        AND (
            (universo.bucket = 'A' AND candidato_top.distancia <= 0.022)
            OR (universo.bucket = 'B' AND candidato_top.distancia <= 0.018)
        )
),

deltas AS (
    SELECT ROUND(delta, 4) AS delta_min_candidato
    FROM UNNEST(GENERATE_ARRAY(0.0, 0.03, 0.002)) AS delta
)

SELECT
    delta_min_candidato,
    COUNTIF(top1_correcto) AS n_correcto_total,
    COUNTIF(top1_correcto AND (margen IS NULL OR margen < delta_min_candidato))
        AS n_correcto_a_banda_gris,
    COUNTIF(NOT top1_correcto) AS n_incorrecto_total,
    COUNTIF(NOT top1_correcto AND (margen IS NULL OR margen < delta_min_candidato))
        AS n_incorrecto_a_banda_gris
FROM aceptados_por_distancia
CROSS JOIN deltas
GROUP BY delta_min_candidato
ORDER BY delta_min_candidato;

-- Paso 4: proyeccion de banda gris sobre el universo COMPLETO de
-- int_candidatos_producto (240,400 producto_key), tau_alto=0.022 (A) /
-- 0.018 (B) y delta_min=0.008 fijos, sweep de tau_bajo por bucket desde
-- tau_alto. Resultado: el minimo posible -tau_bajo = tau_alto, sin
-- ensanchar nada- YA da 1,845 (A) + 728 (B) = 2,573 filas de banda gris,
-- por encima del presupuesto de ~2,000 de Sanfer. Ensanchar 0.004 mas en B
-- lo sube a 2,881: no hay margen para dar holgura con esta densidad de
-- candidatos, asi que tau_bajo se fija IGUAL a tau_alto en los dos
-- buckets -a diferencia de Sanfer, que si tenia holgura hasta 0.055-.
WITH bucket_tienda AS (
    SELECT tienda_key,
        CASE
            WHEN tienda_slug IN (
                'gi', 'klyns', 'isseg', 'aurrera', 'heb', 'farmatodo',
                'guadalajara', 'benavides', 'walmart'
            ) THEN 'A'
            ELSE 'B'
        END AS bucket
    FROM `scenic-firefly-473823-f7.precios_gold.dim_tienda`
),

candidato_top AS (
    SELECT
        bucket_tienda.bucket,
        c.ndf_id,
        c.distancia,
        (
            c.distancia <= IF(bucket_tienda.bucket = 'A', 0.022, 0.018)
            AND (c.margen IS NOT NULL AND c.margen >= 0.008)
            AND c.es_reciproco
            AND (c.atributos_producto.dosis_mg IS NULL OR c.atributos_ndf.dosis_mg IS NULL
                 OR c.atributos_producto.dosis_mg = c.atributos_ndf.dosis_mg)
            AND (c.atributos_producto.volumen_ml IS NULL OR c.atributos_ndf.volumen_ml IS NULL
                 OR c.atributos_producto.volumen_ml = c.atributos_ndf.volumen_ml)
            AND (c.atributos_producto.masa_g IS NULL OR c.atributos_ndf.masa_g IS NULL
                 OR c.atributos_producto.masa_g = c.atributos_ndf.masa_g)
            AND (c.atributos_producto.piezas IS NULL OR c.atributos_ndf.piezas IS NULL
                 OR c.atributos_producto.piezas = c.atributos_ndf.piezas)
        ) AS aceptado
    FROM `scenic-firefly-473823-f7.precios_ml.int_candidatos_producto` AS c
    INNER JOIN bucket_tienda ON bucket_tienda.tienda_key = c.tienda_key
    WHERE c.rank_desde_producto = 1
),

tau_bajo_candidatos AS (
    SELECT ROUND(tau_bajo, 4) AS tau_bajo
    FROM UNNEST(GENERATE_ARRAY(0.018, 0.024, 0.0005)) AS tau_bajo
)

SELECT
    candidato_top.bucket,
    tau_bajo_candidatos.tau_bajo,
    COUNTIF(candidato_top.aceptado) AS n_aceptado,
    COUNTIF(
        NOT candidato_top.aceptado
        AND candidato_top.distancia <= tau_bajo_candidatos.tau_bajo
    ) AS n_banda_gris
FROM candidato_top
CROSS JOIN tau_bajo_candidatos
GROUP BY candidato_top.bucket, tau_bajo_candidatos.tau_bajo
ORDER BY candidato_top.bucket, tau_bajo_candidatos.tau_bajo;
