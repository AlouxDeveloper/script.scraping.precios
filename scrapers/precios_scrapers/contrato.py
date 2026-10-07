"""Contrato de salida v1 de Scrapers 2.0: única fuente del esquema.

Implementa la sección 4.3 del PRD. Versionado (sección 4.5): PATCH para
documentación o validaciones sin cambio de esquema; MINOR para una columna
nullable nueva o una clave promovida desde ``atributos_tienda``; MAJOR para
renombrar, cambiar tipo o semántica, y se acuerda antes con Aldo. Una prueba
falla si ``ESQUEMA`` cambia sin subir ``CONTRATO_VERSION``.

Los campos particulares de cada tienda (sección 4.4: ``precio_lealtad``,
``promocion``, ``vendedor``, ``requiere_receta``, ``laboratorio``,
``presentacion``, ``stock_cantidad``, ``precio_unitario``,
``cotizacion_requerida``) van como texto dentro de ``atributos_tienda``.
"""
import pyarrow as pa

CONTRATO_VERSION = "1.0.0"

PRECIO = pa.decimal128(12, 2)

ESQUEMA = pa.schema(
    [
        pa.field("contrato_version", pa.string(), nullable=False),
        pa.field("corrida_id", pa.string(), nullable=False),
        pa.field("tienda", pa.string(), nullable=False),
        pa.field("capturado_en", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("url_producto", pa.string(), nullable=False),
        pa.field("sku_tienda", pa.string(), nullable=False),
        pa.field("producto", pa.string(), nullable=False),
        pa.field("marca", pa.string()),
        pa.field("ean", pa.string()),
        pa.field("categoria_ruta", pa.list_(pa.string())),
        pa.field("precio_lista", PRECIO),
        pa.field("precio_oferta", PRECIO),
        pa.field("moneda", pa.string(), nullable=False),
        pa.field("disponible", pa.bool_()),
        pa.field("url_imagen", pa.string()),
        pa.field("zona_precio", pa.string()),
        pa.field("escalon", pa.string(), nullable=False),
        pa.field("url_fuente", pa.string(), nullable=False),
        pa.field("atributos_tienda", pa.map_(pa.string(), pa.string())),
    ],
    metadata={"contrato_version": CONTRATO_VERSION},
)
