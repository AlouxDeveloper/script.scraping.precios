{#
    Vista de staging del catálogo NDF: aquí el catálogo deja de ser texto.
    Bronce lo guarda todo en STRING a propósito; el tipado vive en dbt, junto
    a la regla que lo justifica.

    Solo se tipan tres cosas; el resto queda STRING tal cual llega:

    - `fecha_lanzamiento`: de `YYYYMM` a DATE. El centinela `190012` ("sin
      fecha de lanzamiento conocida", no diciembre de 1900) se vuelve NULL.
    - `std_fac`: a NUMERIC. Es la única columna del catálogo con nulos (145).
    - `ndf_id`: se conserva STRING y SIN padding, tal como viene. Cualquier
      crosswalk que llegue con ceros a la izquierda hay que normalizarlo
      antes de joinear contra esta llave — es un bloqueo abierto del
      contrato con Knobloch.
#}

select
    ndf_id,

    -- `parse_date('%Y%m', NULL)` devuelve NULL, así que el `nullif` del
    -- centinela basta para no arrastrar la fecha de 1900.
    parse_date('%Y%m', nullif(fecha_lanzamiento, '190012')) as fecha_lanzamiento,

    -- `safe_cast` en vez de `cast`: los 180,769 valores actuales convierten
    -- limpio, pero un export futuro con basura no debe reventar el build.
    safe_cast(std_fac as numeric) as std_fac,

    presentacion,
    producto,
    descripcion,
    cve_laboratorio,
    laboratorio,
    corporacion,
    cve_mg,
    cve_genero,
    genero,
    cve_ct,
    cve_ff,
    forma_farmaceutica_n3,
    molecula,
    division

from {{ source('bronce', 'ndf_ext') }}
