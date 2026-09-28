{#
    Valida macros/mg_por_envase.sql contra presentaciones reales del
    catálogo NDF, pasadas por `limpiar_texto` igual que en
    `int_ndf_grupo_competitivo`. Cubre el caso de validación del PRD
    (Bisolvon Infantil 4 mg/5 ml × 120 ml = 96 mg), un sólido, una
    concentración por ml sin número y los tres casos que deben quedar NULL.

    Falla si algún caso no reproduce mg_por_unidad, unidad o mg_por_envase.
#}

with casos as (

    select * from unnest([
        struct(
            'BISOLVON LINCTUS 4 MG /5ML 120 ML + ACCE' as texto,
            0.8 as mg_por_unidad_esperado,
            'MG/ML' as unidad_esperada,
            96.0 as mg_por_envase_esperado
        ),
        struct('TABALON TABL 400 MG 10', 400.0, 'MG', 4000.0),
        struct('DORZOLAMINA G.I EX SOL OFTA 20 MG /ML 5 ML', 20.0, 'MG/ML', 100.0),
        -- Líquido sin concentración: los 500 mg son por cada 5 ml, no por envase.
        struct('AMOXICILINA G.I MA SUSP 500 MG 60 ML', null, null, null),
        -- Empaque doble: el "2" rompe el patrón y no se adivina.
        struct('BISOLVON LINCTUS PED. 4 MG /5ML 2 100 ML', null, null, null),
        struct('MOTRIN GOTA PED FSA 50 MG 15ML CHAR 2 6', null, null, null)
    ])

),

evaluado as (

    select
        casos.*,
        {{ mg_por_envase(limpiar_texto('casos.texto')) }} as magnitud
    from casos

)

select *
from evaluado
where
    magnitud.mg_por_unidad is distinct from cast(mg_por_unidad_esperado as numeric)
    or magnitud.unidad is distinct from unidad_esperada
    or magnitud.mg_por_envase is distinct from cast(mg_por_envase_esperado as numeric)
