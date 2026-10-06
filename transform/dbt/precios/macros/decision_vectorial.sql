{#
    La regla de decisión del entity resolution vectorial (ALD-93), como
    expresión `case` sobre las columnas de `int_candidato_evaluado`.
    Vive en un macro para que `int_match_ndf` (producción) y
    `rev_er_calibracion` (la curva que recalibra los `tau`) apliquen
    exactamente la misma regla: si la calibración midiera otra cosa, sus
    números no dirían nada del modelo.

    `tau_farma` y `tau_no_farma` son parámetros y no los vars directos
    porque la calibración los barre; producción pasa los vars. El resto
    (`delta_min`, guarda, marca, `cuarentena_forzada`) queda fijo. Ver el
    docstring de `int_match_ndf` para el porqué de cada condición.
#}
{% macro decision_vectorial(tau_farma, tau_no_farma) %}
    case
        when ndf_id is null then 'sin_match'
        when not marca_ok then 'sin_match'
        when distancia > (
            case
                when division = 'FARMA' then {{ tau_farma }}
                else {{ tau_no_farma }}
            end
        ) then 'sin_match'
        when margen >= {{ var('delta_min') }}
            and guarda_ok
            and not es_cuarentena_forzada
            then 'vectorial'
        else 'cuarentena'
    end
{% endmacro %}
