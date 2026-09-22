-- Solapamiento lexico de las tres variantes de texto_er_ndf.sql (ALD-64)
-- contra dim_producto.descripcion, sobre los 61,085 pares verdaderos de
-- aportadores (todos los laboratorios, mismo criterio que ALD-84: la
-- geometria no depende del laboratorio). Filtro previo a la medicion
-- vectorial -descarta variantes obviamente peores antes de generar tres
-- juegos de ~180,914 vectores. Corrida de referencia 2026-09-22.
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/10_solape_variantes_texto_ndf.sql
--
-- Replica limpiar_texto.sql en SQL plano (sin Jinja) como funcion temporal,
-- para normalizar los campos crudos del catalogo (presentacion, producto,
-- descripcion, laboratorio, forma_farmaceutica_n3, molecula no pasan por
-- el macro en produccion) igual que se normaliza dim_producto.descripcion.
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
        p.descripcion as descripcion_tienda,
        -- upper() en las tres: limpiar_texto_sql devuelve minusculas y
        -- descripcion_tienda ya viene en mayusculas de produccion. Sin
        -- esto la comparacion de tokens es case-sensitive y casi ningun
        -- token de palabra cruza -bug real de la primera corrida
        -- (2026-09-22), encontrado y corregido el mismo dia en ALD-85.
        upper(limpiar_texto_sql(n.presentacion)) as v1,
        upper(limpiar_texto_sql(
            n.producto || ' ' || n.descripcion || ' ' || n.laboratorio
        )) as v2,
        upper(limpiar_texto_sql(
            n.presentacion || ' ' || n.forma_farmaceutica_n3 || ' ' || n.molecula
        )) as v3
    from `scenic-firefly-473823-f7.precios_gold.dim_producto` as p
    inner join `scenic-firefly-473823-f7.precios_gold.dim_ndf` as n
        on n.ndf_id = p.ndf_id
    where p.match_method = 'aportadores'

),

tokenizado as (

    select
        array(select distinct t from unnest(split(descripcion_tienda, ' ')) as t where t != '')
            as tokens_tienda,
        array(select distinct t from unnest(split(v1, ' ')) as t where t != '') as tokens_v1,
        array(select distinct t from unnest(split(v2, ' ')) as t where t != '') as tokens_v2,
        array(select distinct t from unnest(split(v3, ' ')) as t where t != '') as tokens_v3
    from pares

)

-- Resultado: v1 (solo presentacion) tiene el mayor solape -confirma la
-- hipotesis de trabajo del issue. v2 (agrega laboratorio) empeora: el
-- fabricante casi nunca aparece en la descripcion de tienda, mete una
-- palabra mas al denominador de Jaccard sin sumar al numerador. v3 (agrega
-- forma_farmaceutica_n3 y molecula) tambien empeora, y por la misma razon
-- -son campos de catalogo, no vocabulario de tienda.
select
    'v1_presentacion' as variante,
    round(avg(jaccard(tokens_tienda, tokens_v1)), 4) as jaccard_prom,
    round(approx_quantiles(jaccard(tokens_tienda, tokens_v1), 2)[offset(1)], 4)
        as jaccard_mediana
from tokenizado
union all
select
    'v2_producto_descripcion_laboratorio',
    round(avg(jaccard(tokens_tienda, tokens_v2)), 4),
    round(approx_quantiles(jaccard(tokens_tienda, tokens_v2), 2)[offset(1)], 4)
from tokenizado
union all
select
    'v3_presentacion_forma_molecula',
    round(avg(jaccard(tokens_tienda, tokens_v3)), 4),
    round(approx_quantiles(jaccard(tokens_tienda, tokens_v3), 2)[offset(1)], 4)
from tokenizado
order by jaccard_prom desc;
