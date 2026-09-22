-- Estilo de descripcion por tienda (ALD-84): mide si dim_producto.descripcion
-- varia lo bastante entre tiendas como para justificar un umbral por tienda
-- (o por bucket) en vez de uno global. Corrida de referencia 2026-09-22,
-- sobre TODO el set de aportadores (61,085 pares, no solo Sanfer) -la
-- geometria "descripcion de tienda X contra presentacion NDF" no depende
-- del laboratorio, calibrar solo con Sanfer dejaria muy poca n por tienda.
--
-- Se corre a mano, desde la raiz del repo:
--   bq query --use_legacy_sql=false \
--     < transform/entity_resolution/sql/09_estilo_descripcion_por_tienda.sql
--
-- Replica limpiar_texto.sql en SQL plano (sin Jinja, para bq CLI directo):
-- dim_ndf.presentacion no pasa por el macro en produccion, se normaliza
-- aqui para comparar tokens manzana con manzana contra descripcion.

with normalizado as (

    select
        dim_tienda.tienda_slug,
        p.descripcion as descripcion_norm,
        -- upper() al final: descripcion_norm (dim_producto.descripcion) ya
        -- viene en mayusculas de produccion. Sin este upper() la
        -- comparacion de tokens es case-sensitive entre mayusculas y
        -- minusculas y casi ningun token de palabra cruza -solo los
        -- numeros, que no tienen case- inflando artificialmente el
        -- "estilo distinto" que este script mide. Bug real de la primera
        -- corrida (2026-09-22), corregido el mismo dia tras detectarlo en
        -- ALD-85.
        upper(trim(regexp_replace(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(
                            normalize(lower(trim(n.presentacion)), NFD),
                            r'\pM', ''
                        ),
                        r'(\d)\.(\d)', r'\1qzpuntodecimalqz\2'
                    ),
                    r'[^\p{L}\p{N} ]', ' '
                ),
                r'qzpuntodecimalqz', '.'
            ),
            r' +', ' '
        ))) as presentacion_norm
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
        length(descripcion_norm) as descripcion_chars,
        length(presentacion_norm) as presentacion_chars,
        array(
            select distinct t from unnest(split(descripcion_norm, ' ')) as t
            where t != ''
        ) as tokens_descripcion,
        array(
            select distinct t from unnest(split(presentacion_norm, ' ')) as t
            where t != ''
        ) as tokens_presentacion
    from normalizado

),

metrico as (

    select
        tienda_slug,
        descripcion_chars,
        presentacion_chars,
        array_length(tokens_descripcion) as n_tokens_descripcion,
        array_length(tokens_presentacion) as n_tokens_presentacion,
        (
            select count(*) from unnest(tokens_presentacion) as tp
            where tp in unnest(tokens_descripcion)
        ) as n_interseccion,
        array_length(tokens_descripcion) + array_length(tokens_presentacion)
            - (
                select count(*) from unnest(tokens_presentacion) as tp
                where tp in unnest(tokens_descripcion)
            ) as n_union
    from tokenizado

)

-- Resultado (2026-09-22): jaccard_prom va de 0.0173 (sanpablo) a 0.1093
-- (gi) -rango de ~6x, con sanpablo aislado muy por debajo del resto
-- (siguiente mas bajo, chedraui, esta a 3x de distancia). Confirma variacion
-- real de estilo entre tiendas: un umbral global asumiria que la misma
-- distancia coseno significa lo mismo en las 19, y no es cierto.
select
    tienda_slug,
    count(*) as n_pares,
    round(avg(descripcion_chars), 1) as descripcion_chars_prom,
    round(avg(presentacion_chars), 1) as presentacion_chars_prom,
    round(avg(n_tokens_descripcion), 1) as descripcion_tokens_prom,
    round(avg(n_tokens_presentacion), 1) as presentacion_tokens_prom,
    round(avg(safe_divide(n_interseccion, n_union)), 4) as jaccard_prom,
    round(approx_quantiles(safe_divide(n_interseccion, n_union), 2)[offset(1)], 4)
        as jaccard_mediana,
    round(avg(safe_divide(n_interseccion, n_tokens_presentacion)), 4)
        as frac_presentacion_en_descripcion_prom
from metrico
group by tienda_slug
order by jaccard_prom desc;

-- n_pares por tienda, las 19 completas (incluye las que no aparecen arriba
-- por no tener ningun par match_method = 'aportadores'). Resultado: fesa,
-- similares, fahorro, soriana, alsuper y farmalisto en CERO -no 1-12 como
-- decia el issue original, sino sin ground truth alguno-; yza en 1, thin de
-- verdad. Ninguna de las 6 en cero puede calibrar ni un umbral propio ni
-- una asignacion de bucket medida: van al bucket por defecto.
select
    dim_tienda.tienda_slug,
    count(p.producto_key) as n_pares
from `scenic-firefly-473823-f7.precios_gold.dim_tienda` as dim_tienda
left join `scenic-firefly-473823-f7.precios_gold.dim_producto` as p
    on p.tienda_key = dim_tienda.tienda_key and p.match_method = 'aportadores'
group by dim_tienda.tienda_slug
order by n_pares asc;
