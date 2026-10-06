{#
    Miligramos de principio activo por unidad y por envase de una
    presentación del NDF (M7, ALD-101). Recibe el texto ya pasado por
    `limpiar_texto`: sin la diagonal, "4 MG /5ML 120 ML" llega como
    "4 mg 5ml 120 ml".

    Devuelve STRUCT<mg_por_unidad NUMERIC, unidad STRING, mg_por_envase
    NUMERIC>:

    - Líquidos con concentración explícita ("X MG /n ML V ML"): X/n mg por
      ml y X/n·V por envase. Sin n ("100 MG /ML 15 ML") el denominador es 1
      ml. `unidad` = 'MG/ML'.
    - Sólidos (el texto no menciona ml): la dosis y las piezas de
      `extraer_atributos`, dosis × piezas. `unidad` = 'MG'.
    - Cualquier otro caso es NULL: un líquido sin concentración ("SUSP 500
      MG 60 ML") o un empaque múltiple ("4 MG /5ML 2 100 ML") no se adivina.

    Se calcula sobre la presentación del NDF y no sobre la etiqueta de la
    tienda: Bisolvon Infantil se anuncia como "80 mg", "96 mg" o "4 mg"
    según la cadena. `extraer_atributos` se reutiliza sin tocarla porque es
    la guarda del entity resolution.

    ponytail: en sólidos con dos cantidades ("20+20") `piezas` toma el
    último número; el grupo competitivo (misma molécula y mg por unidad)
    limita el daño, y la auditoría de presentaciones Sanfer dirá si hace
    falta una regla propia.
#}
{% macro mg_por_envase(columna) %}
    {%- set num = '\\d+(?:\\.\\d+)?' -%}
    (
        select as struct
            if(
                liquido.mg is not null,
                liquido.mg / liquido.ml_dosis,
                if(solido.volumen_ml is null, solido.dosis_mg, null)
            ) as mg_por_unidad,
            case
                when liquido.mg is not null then 'MG/ML'
                when solido.volumen_ml is null and solido.dosis_mg is not null
                    then 'MG'
            end as unidad,
            if(
                liquido.mg is not null,
                liquido.mg / liquido.ml_dosis * liquido.ml_envase,
                if(solido.volumen_ml is null, solido.dosis_mg * solido.piezas, null)
            ) as mg_por_envase
        from unnest([struct(
            safe_cast(regexp_extract(
                upper({{ columna }}),
                r'({{ num }})\s*MG\s+(?:{{ num }})?\s*ML\s+{{ num }}\s*ML\b'
            ) as numeric) as mg,
            coalesce(safe_cast(regexp_extract(
                upper({{ columna }}),
                r'{{ num }}\s*MG\s+({{ num }})?\s*ML\s+{{ num }}\s*ML\b'
            ) as numeric), 1) as ml_dosis,
            safe_cast(regexp_extract(
                upper({{ columna }}),
                r'{{ num }}\s*MG\s+(?:{{ num }})?\s*ML\s+({{ num }})\s*ML\b'
            ) as numeric) as ml_envase
        )]) as liquido,
        unnest([{{ extraer_atributos(columna) }}]) as solido
    )
{% endmacro %}
