-- Solapamiento lexico de t1 (descripcion tal cual) contra t2 (nucleo
-- recortado + magnitudes normalizadas) de texto_er_tienda.sql (ALD-85),
-- contra dim_ndf.presentacion (v1, confirmado en ALD-64), por tienda,
-- sobre los 61,085 pares verdaderos de aportadores. Corrida de referencia
-- 2026-09-22.
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/11_solape_variantes_texto_tienda.sql
--
-- t2 replicado en SQL plano (sin Jinja) para bq CLI directo -misma lista
-- de relleno y misma logica de magnitudes que macros/texto_er_tienda.sql;
-- ver ese archivo si la lista cambia, para no divergir. El espacio antes
-- de la unidad en las magnitudes normalizadas ("500 MG", no "500MG") es a
-- proposito: pegado nunca coincide con un token de presentacion, que
-- siempre trae numero y unidad separados -medido, no adivinado: la
-- version sin espacio bajaba el Jaccard en vez de subirlo.
--
-- Resultado: mixto, no una victoria pareja de t2. Sube claro en chedraui
-- (0.249->0.350, la ganancia mas grande, confirma la hipotesis del relleno
-- de marketing) y sube modesto en comer/sanpablo/heb/farmatodo. Baja en
-- las tiendas que ya escribian mas concisas (gi, klyns, aurrera, isseg,
-- benavides, walmart, guadalajara): ahi las magnitudes normalizadas que
-- se agregan casi siempre duplican algo que ya estaba en el mismo formato,
-- e inflan el denominador de Jaccard sin sumar match nuevo. Consistente
-- con la advertencia del issue de "no pasarse". El default se queda en t1
-- -la medicion vectorial, no esta, es la que decide si t2 se adopta.
CREATE TEMP FUNCTION extraer_dosis_mg(texto STRING) AS ((
    COALESCE(
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*MG\b') AS NUMERIC),
        SAFE_DIVIDE(SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*MCG\b') AS NUMERIC), 1000),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*G\b') AS NUMERIC) * 1000
    )
));

CREATE TEMP FUNCTION extraer_volumen_ml(texto STRING) AS ((
    COALESCE(
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*ML\b') AS NUMERIC),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*L\b') AS NUMERIC) * 1000
    )
));

CREATE TEMP FUNCTION extraer_masa_g(texto STRING) AS ((
    COALESCE(
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*G\b') AS NUMERIC),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*GR\b') AS NUMERIC),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+(?:\.\d+)?)\s*KG\b') AS NUMERIC) * 1000
    )
));

CREATE TEMP FUNCTION extraer_piezas(texto STRING) AS ((
    COALESCE(
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+)\s*TAB[A-Z]*\b') AS INT64),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+)\s*CAP[A-Z]*\b') AS INT64),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+)\s*GRAG[A-Z]*\b') AS INT64),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+)\s*PZ[A-Z]*\b') AS INT64),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'\bC\s+(\d+)\b') AS INT64),
        SAFE_CAST(REGEXP_EXTRACT(UPPER(texto), r'(\d+)\s*$') AS INT64)
    )
));

CREATE TEMP FUNCTION texto_t2(descripcion STRING) AS ((
    TRIM(REGEXP_REPLACE(
        CONCAT(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        UPPER(descripcion),
                        r'\b(DE|DEL|LA|EL|LOS|LAS|EN|CON|PARA|POR|Y|A|AL|SIN|SU|SUS)\b', ' '
                    ),
                    r'\b(CAJA|ENVASE|FRASCO|TUBO|PAQUETE|BLISTER)\b', ' '
                ),
                r'\b(PREMIUM|EXPRESS|EXTRA|OPTIMAL|CLINICAL|ORIGINAL|NUEVO|NUEVA|MEJORADO|MEJORADA)\b', ' '
            ),
            ' ',
            -- El espacio antes de la unidad importa: pegado ("500MG") no
            -- coincide con ningun token de presentacion, que siempre trae
            -- el numero y la unidad separados.
            COALESCE(CONCAT(CAST(extraer_dosis_mg(descripcion) AS STRING), ' MG'), ''),
            ' ',
            COALESCE(CONCAT(CAST(extraer_volumen_ml(descripcion) AS STRING), ' ML'), ''),
            ' ',
            COALESCE(CONCAT(CAST(extraer_masa_g(descripcion) AS STRING), ' G'), ''),
            ' ',
            COALESCE(CONCAT(CAST(extraer_piezas(descripcion) AS STRING), ' PZ'), '')
        ),
        r' +', ' '
    ))
));

-- presentacion no pasa por limpiar_texto en produccion (igual que en
-- 09_estilo_descripcion_por_tienda.sql y 10_solape_variantes_texto_ndf.sql):
-- se normaliza aqui para no comparar tokens con puntuacion cruda del
-- catalogo contra tokens ya limpios del lado tienda.
CREATE TEMP FUNCTION limpiar_texto_sql(texto STRING) AS ((
    TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        NORMALIZE(LOWER(TRIM(texto)), NFD),
                        r'\pM', ''
                    ),
                    r'(\d)\.(\d)', r'\1qzpuntodecimalqz\2'
                ),
                r'[^\p{L}\p{N} ]', ' '
            ),
            r'qzpuntodecimalqz', '.'
        ),
        r' +', ' '
    ))
));

CREATE TEMP FUNCTION jaccard(tokens_a ARRAY<STRING>, tokens_b ARRAY<STRING>) AS ((
    SAFE_DIVIDE(
        (SELECT COUNT(*) FROM UNNEST(tokens_a) AS t WHERE t IN UNNEST(tokens_b)),
        ARRAY_LENGTH(tokens_a) + ARRAY_LENGTH(tokens_b)
            - (SELECT COUNT(*) FROM UNNEST(tokens_a) AS t WHERE t IN UNNEST(tokens_b))
    )
));

with pares as (

    select
        dim_tienda.tienda_slug,
        p.descripcion as t1,
        texto_t2(p.descripcion) as t2,
        upper(limpiar_texto_sql(n.presentacion)) as presentacion
    from `scenic-firefly-473823-f7.precios_gold.dim_producto` as p
    inner join `scenic-firefly-473823-f7.precios_gold.dim_ndf` as n
        on n.ndf_id = p.ndf_id
    inner join `scenic-firefly-473823-f7.precios_gold.dim_tienda` as dim_tienda
        on dim_tienda.tienda_key = p.tienda_key
    where p.match_method = 'aportadores'

),

tokenizado as (

    select
        tienda_slug,
        array(select distinct t from unnest(split(t1, ' ')) as t where t != '') as tokens_t1,
        array(select distinct t from unnest(split(t2, ' ')) as t where t != '') as tokens_t2,
        array(select distinct t from unnest(split(presentacion, ' ')) as t where t != '')
            as tokens_presentacion
    from pares

)

select
    tienda_slug,
    count(*) as n_pares,
    round(avg(safe_divide(
        (select count(*) from unnest(tokens_t1) as t where t in unnest(tokens_presentacion)),
        array_length(tokens_t1) + array_length(tokens_presentacion)
            - (select count(*) from unnest(tokens_t1) as t where t in unnest(tokens_presentacion))
    )), 4) as jaccard_t1,
    round(avg(safe_divide(
        (select count(*) from unnest(tokens_t2) as t where t in unnest(tokens_presentacion)),
        array_length(tokens_t2) + array_length(tokens_presentacion)
            - (select count(*) from unnest(tokens_t2) as t where t in unnest(tokens_presentacion))
    )), 4) as jaccard_t2
from tokenizado
group by tienda_slug
order by jaccard_t2 - jaccard_t1 desc;
