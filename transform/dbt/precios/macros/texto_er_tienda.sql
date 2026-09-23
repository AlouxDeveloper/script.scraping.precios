{#
    Compone el texto de tienda que se vectoriza en el entity resolution (ver
    ALD-85). Gemelo de `texto_er_ndf.sql`, pero del lado que de verdad
    varía: `presentacion` del catálogo es corta y densa; la descripción de
    tienda es larga y con relleno de marketing y de empaque, y ese relleno
    desplaza el vector sin aportar señal -es exactamente la asimetría que
    obliga al ajuste por tienda de ALD-84.

    `t1` (default) es la línea base: `descripcion` tal cual, ya normalizada
    por `limpiar_texto` y en mayúsculas desde `stg_precios`. **El default
    se queda en t1 hasta que la medición vectorial diga otra cosa** -el
    solapamiento léxico de ALD-85 es un filtro previo, no el criterio que
    decide.

    `t2` recorta relleno (preposiciones españolas, envase, un puñado de
    adjetivos de marketing observados en el histórico) y le pega al final
    las magnitudes normalizadas de `extraer_atributos` -mismo valor, mismo
    formato con espacio ("500 MG"), sin importar si la tienda escribió
    "500 mg", "0.5 g" o "500mg". El espacio importa: pegado ("500MG") no
    coincide con ningún token de `presentacion`, que siempre separa número
    y unidad -medido en ALD-85, la versión sin espacio bajaba el
    solapamiento léxico en vez de subirlo. Llama a `extraer_atributos`
    cuatro veces (una por
    atributo) sobre el mismo texto: repite el regex, no el resultado, y a
    240 mil filas una sola vez es barato comparado con lo que se evita -
    pagar la API de embeddings sobre una variante que la medición todavía
    no justifica.

    Lista de relleno deliberadamente corta -"ojo con no pasarse": recortar
    de más tira tokens que sí distinguen dos presentaciones de la misma
    marca. Se mide t2 contra t1, no se adopta por parecer más limpio.

    ALD-67 cerró la comparación sin correr el barrido vectorial completo:
    el solapamiento léxico de ALD-85 salió mixto (t2 sube en tiendas
    verbosas, baja en tiendas ya concisas), no lo bastante a favor de t2
    como para justificar re-embeber las 240,400 filas de `dim_producto`
    solo para confirmarlo con `rev_er_metricas`. Si la dispersión de
    umbrales entre tiendas resulta alta ahí, esa es la señal concreta
    para reabrir esta comparación con embeddings reales.
#}
{% macro texto_er_tienda(columna) %}
    {%- set variante = var('variante_tienda', 't1') -%}
    {%- if variante == 't1' -%}
        {{ columna }}
    {%- elif variante == 't2' -%}
        trim(regexp_replace(
            concat(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(
                            upper({{ columna }}),
                            -- Preposiciones y artículos: conectores sin
                            -- señal de producto.
                            r'\b(DE|DEL|LA|EL|LOS|LAS|EN|CON|PARA|POR|Y|A|AL|SIN|SU|SUS)\b',
                            ' '
                        ),
                        -- Empaque: el material del envase no es marca ni
                        -- magnitud, y ya está cubierto por separado si la
                        -- tienda también da el peso o volumen.
                        r'\b(CAJA|ENVASE|FRASCO|TUBO|PAQUETE|BLISTER)\b',
                        ' '
                    ),
                    -- Adjetivos de marketing observados en el histórico
                    -- (walmart, aurrera): no describen el producto, lo
                    -- venden.
                    r'\b(PREMIUM|EXPRESS|EXTRA|OPTIMAL|CLINICAL|ORIGINAL|NUEVO|NUEVA|MEJORADO|MEJORADA)\b',
                    ' '
                ),
                ' ',
                coalesce(
                    concat(cast((
                        {{ extraer_atributos(columna) }}
                    ).dosis_mg as string), ' MG'),
                    ''
                ),
                ' ',
                coalesce(
                    concat(cast((
                        {{ extraer_atributos(columna) }}
                    ).volumen_ml as string), ' ML'),
                    ''
                ),
                ' ',
                coalesce(
                    concat(cast((
                        {{ extraer_atributos(columna) }}
                    ).masa_g as string), ' G'),
                    ''
                ),
                ' ',
                coalesce(
                    concat(cast((
                        {{ extraer_atributos(columna) }}
                    ).piezas as string), ' PZ'),
                    ''
                )
            ),
            r' +', ' '
        ))
    {%- else -%}
        {{ exceptions.raise_compiler_error(
            "texto_er_tienda: variante_tienda desconocida '" ~ variante
            ~ "'. Usa t1 o t2."
        ) }}
    {%- endif -%}
{% endmacro %}
