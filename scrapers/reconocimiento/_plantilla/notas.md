# Reconocimiento: {TIENDA}

- **URL:** {URL_HOME}
- **Slug:** {SLUG}
- **Fecha:** {AAAA-MM-DD}
- **Quién:** {persona} (con Claude en Chrome desde Windows nativo)

## Cómo usar esta plantilla

Copiar la carpeta `_plantilla/` a `scrapers/reconocimiento/{SLUG}/` y llenar cada
sección con los prompts P1 a P5 de la sección 3.3 de la Metodología de
reconocimiento (Notion). Lo que no se pudo observar se escribe como "no observado"
o "por verificar", nunca se deja adivinado.

### Convención de evidencia

En el repo, dentro de `scrapers/reconocimiento/{SLUG}/`:

| Archivo | Contenido |
| --- | --- |
| `notas.md` | Este documento, con los hallazgos de P1 a P5. |
| `peticiones.txt` | cURL mínimos copiados de DevTools, sin cookies ni headers de autorización. |
| `muestras/` | Respuestas JSON o HTML recortadas a menos de 50 KB por archivo; luego sirven de fixtures del spider. |
| `validacion.csv` | Salida de `scrapers/reconocimiento/validar_endpoint.py`. |

En GCS, en `gs://raw_precios_bitek/reconocimiento/{SLUG}/{AAAA-MM-DD}/`:

- HAR exportado con "Export HAR (sanitized)" en DevTools; nunca "with sensitive data".
- Capturas y GIF de desafíos o CAPTCHAs.

No van al repo porque pesan y pueden traer datos de sesión. Revisar las capturas
antes de compartirlas: muestran todo lo visible en pantalla.

## Plataforma y protección

<!-- P1: plataforma con su evidencia, nombres de cookies (sin valores) y WAF
     detectado, líneas Disallow relevantes y todas las líneas Sitemap de robots.txt. -->

## Categorías y paginación

<!-- P2: árbol de categorías de farmacia con URL e identificador de cada hoja,
     total de productos reportado, mecanismo de paginación, tamaño de página y tope. -->

## Endpoints

<!-- P3: XHR de listado y de búsqueda (método, URL y parámetros), ruta de cada
     campo en el JSON y parámetros o headers que parezcan firma o token. -->

## Ficha de producto

<!-- P4: JSON embebido (JSON-LD, __NEXT_DATA__ u otro), XHR de detalle, sucursal
     o CP por defecto y cómo se fija, y si el precio visible coincide con el JSON. -->

## Propuesta

<!-- P5: escalón candidato (a, b, c o d) y por qué, estrategia de cobertura completa
     con estimación de peticiones, riesgos y peticiones a validar. Marcar como
     hipótesis lo no verificado. -->
