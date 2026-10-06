{#
    Valida macros/extraer_atributos.sql contra descripciones reales del
    histórico (dim_producto/dim_ndf), no texto inventado: los casos borde que
    importan -concatenación sin espacio, división del catálogo, la palabra
    de forma farmacéutica exacta que usa cada tienda- solo aparecen en datos
    reales. Incluye la pareja "1 G" contra "1000 MG" (misma magnitud, dos
    unidades) para probar la conversión, y una fila sin ninguna magnitud.

    Falla si algún caso no reproduce el valor esperado en dosis_mg,
    volumen_ml, masa_g o piezas.
#}

with casos as (

    select * from unnest([
        struct(
            'KEFLEX 1 G ORAL 12 TABLETAS' as texto,
            1000.0 as dosis_mg_esperado,
            cast(null as numeric) as volumen_ml_esperado,
            1.0 as masa_g_esperado,
            12 as piezas_esperado
        ),
        struct(
            'ELATEC 1000 MG ORAL 20 TABS',
            1000.0,
            cast(null as numeric),
            cast(null as numeric),
            20
        ),
        struct(
            'TRULICITY 0.75 MG 0.5 ML DULAGLUTIDA 4 UD JERINGAS PRELLENADAS',
            0.75,
            0.5,
            cast(null as numeric),
            cast(null as int64)
        ),
        struct(
            'AMAL TABS 8 MG C 10',
            8.0,
            cast(null as numeric),
            cast(null as numeric),
            10
        ),
        struct(
            'KIT PARA NEBULIZADOR',
            cast(null as numeric),
            cast(null as numeric),
            cast(null as numeric),
            cast(null as int64)
        ),
        struct(
            'ENCEPHABOL 200 MG ORAL 24 GRAGEAS',
            200.0,
            cast(null as numeric),
            cast(null as numeric),
            24
        ),
        struct(
            'ENFAMIL 6 A 12 MESES F RMULA INFANTIL CAJA 1.1 KG',
            cast(null as numeric),
            cast(null as numeric),
            1100.0,
            cast(null as int64)
        ),
        struct(
            'SIMILAC F RMULA INFANTIL ETAPA 3 350 GR',
            cast(null as numeric),
            cast(null as numeric),
            350.0,
            cast(null as int64)
        ),
        struct(
            'DUODERM EXTRA THIN SPOTS INFANTIL 5PZAS',
            cast(null as numeric),
            cast(null as numeric),
            cast(null as numeric),
            5
        ),
        struct(
            'RHINOCORT AQUA 32 MCG SUSPENSI N NASAL 120 DOSIS',
            0.032,
            cast(null as numeric),
            cast(null as numeric),
            cast(null as int64)
        ),
        -- Real del catálogo (dim_ndf.descripcion, normalizado): la notación
        -- "DOSIS MG /concentracion ML VOLUMEN TOTAL ML" repite la unidad ML
        -- dos veces -"JBE 250 MG /5ML 60 ML" original. El primer match de
        -- ML es el denominador de la concentración (5), no el volumen del
        -- envase (60). Ver el issue: por esto volumen_ml toma el ÚLTIMO
        -- match, no el primero.
        struct(
            'JBE 250 MG 5ML 60 ML',
            250.0,
            60.0,
            cast(null as numeric),
            cast(null as int64)
        )
    ]) as caso

),

evaluado as (

    select
        casos.texto,
        casos.dosis_mg_esperado,
        casos.volumen_ml_esperado,
        casos.masa_g_esperado,
        casos.piezas_esperado,
        atributos.*
    from casos
    left join unnest([{{ extraer_atributos('casos.texto') }}]) as atributos

)

select *
from evaluado
where
    dosis_mg is distinct from dosis_mg_esperado
    or volumen_ml is distinct from volumen_ml_esperado
    or masa_g is distinct from masa_g_esperado
    or piezas is distinct from piezas_esperado
