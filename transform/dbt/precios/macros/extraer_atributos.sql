{#
    Extrae dosis_mg, volumen_ml, masa_g y piezas de un texto ya normalizado
    (salida de limpiar_texto: sin acentos, con el punto decimal protegido).
    Es la guarda de presentación del entity resolution vectorial (ver
    ALD-69): el coseno no distingue "PARACETAMOL 500 MG" de
    "PARACETAMOL 750 MG" -son casi el mismo texto y dos ndf_id distintos-,
    así que la comparación de magnitudes se hace aparte, en SQL, no en el
    embedding.

    Devuelve un STRUCT<dosis_mg NUMERIC, volumen_ml NUMERIC, masa_g NUMERIC,
    piezas INT64>, para llamarse una vez por lado (catálogo y tienda) y
    comparar campo a campo. Un campo NULL significa "no declarado", no cero
    -la regla de aplicación (¿penaliza discordancia, ignora ausencia?) vive
    en el modelo que usa este macro, no aquí.

    `\b` (límite de palabra) después de cada unidad es lo que evita que
    "GR" (masa) matchee dentro de "GRAGEAS" (pieza) o que "G" (masa/dosis)
    matchee dentro de "MG"/"KG": el límite exige que el siguiente carácter
    no sea otra letra o dígito. No hace falta protegerse en el otro extremo
    -entre el número y la unidad-: un dígito y una letra nunca comparten
    "límite de palabra" en regex (ambos son \w), así que num+unidad pegados
    ("500MG", "5PZAS") ya funcionan sin espacio de por medio.
#}
{% macro extraer_atributos(columna) %}
    struct(
        -- dosis_mg: mg tal cual: mcg -> mg (÷1000, la mcg es mil veces más
        -- chica); g suelto -> mg (×1000). El orden de la cadena de COALESCE
        -- no importa entre sí -son patrones mutuamente excluyentes por
        -- diseño- pero mg va primero por ser, con mucho, el más frecuente.
        coalesce(
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*MG\b') as numeric),
            safe_divide(
                safe_cast(regexp_extract(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*MCG\b') as numeric),
                1000
            ),
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*G\b') as numeric) * 1000
        ) as dosis_mg,

        -- volumen_ml: ml tal cual; l suelto -> ml (×1000). Toma el ÚLTIMO
        -- match, no el primero: el catálogo escribe las soluciones como
        -- "DOSIS MG /CONCENTRACION ML VOLUMEN TOTAL ML" (ej. "250 MG /5ML
        -- 60 ML" = 250 mg por cada 5 ml, envase de 60 ml) -el primer ML es
        -- el denominador de la concentración, casi siempre chico, y el
        -- volumen real del envase es el que viene al final. Medido contra
        -- el ground truth de ALD-69: tomar el último bajó la discordancia
        -- de 2.84% a 0.69%. dosis_mg no se cambió a "último" porque ahí no
        -- mejoraba -los combos de dos principios activos (ej. paracetamol +
        -- tramadol) no siguen un orden tan predecible como concentración
        -- antes que volumen.
        coalesce(
            safe_cast(
                (
                    select valor
                    from unnest(
                        regexp_extract_all(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*ML\b')
                    ) as valor with offset posicion
                    order by posicion desc
                    limit 1
                ) as numeric
            ),
            safe_cast(
                (
                    select valor
                    from unnest(
                        regexp_extract_all(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*L\b')
                    ) as valor with offset posicion
                    order by posicion desc
                    limit 1
                ) as numeric
            ) * 1000
        ) as volumen_ml,

        -- masa_g: g y gr son la misma unidad -gramos-, dos abreviaturas
        -- distintas del catálogo; kg -> g (×1000). Un "g" suelto alimenta
        -- esta columna Y dosis_mg a la vez -a propósito: el catálogo no
        -- distingue si un gramo es una dosis (polvo para reconstituir) o
        -- una masa de envase (crema), y separarlos aquí perdería el caso
        -- correcto tanto como ganaría descartar el incorrecto.
        coalesce(
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*G\b') as numeric),
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*GR\b') as numeric),
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+(?:\.\d+)?)\s*KG\b') as numeric) * 1000
        ) as masa_g,

        -- piezas: unidades de forma farmacéutica (tabletas, cápsulas,
        -- grageas) y pzas/pz primero -son la señal más confiable porque
        -- nombran la unidad explícitamente. "TAB"/"CAP"/"GRAG"/"PZ" son
        -- prefijos, no la palabra completa: el catálogo y las tiendas
        -- alternan "TABS"/"TABLETAS"/"TABL" para la misma cosa.
        -- "C <numero>" es el patrón que queda de "C/10" una vez que
        -- limpiar_texto convierte la diagonal en espacio -riesgoso si
        -- apareciera una "C" suelta por otra razón, pero es la señal que
        -- pide el issue y no se ha visto ese falso positivo en la muestra
        -- revisada. El número suelto al final del texto es el último
        -- recurso, ya sin nombre de unidad que lo respalde.
        coalesce(
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+)\s*TAB[A-Z]*\b') as int64),
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+)\s*CAP[A-Z]*\b') as int64),
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+)\s*GRAG[A-Z]*\b') as int64),
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+)\s*PZ[A-Z]*\b') as int64),
            safe_cast(regexp_extract(upper({{ columna }}), r'\bC\s+(\d+)\b') as int64),
            safe_cast(regexp_extract(upper({{ columna }}), r'(\d+)\s*$') as int64)
        ) as piezas
    )
{% endmacro %}
