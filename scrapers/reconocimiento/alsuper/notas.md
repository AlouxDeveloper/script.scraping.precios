# Reconocimiento: Alsuper

- **URL:** https://www.alsuper.com
- **Slug:** alsuper
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); pendiente Aldo con Claude in Chrome
  para términos de uso y precio en pantalla
- **Entorno:** solo oficina

Se reconoció por HTTP leyendo el bundle de Angular del sitio: de ahí salen el host de la API, las
rutas y la sucursal por defecto. El legado ya usaba esta API, pero sus URLs vivían en un Excel
(`salida/urls/urls_categorias_alsuper.xlsx`) que ya no está en el equipo; aquí quedan documentadas.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** frontend propio en Angular (`main-*.js` y `chunk-*.js`) sobre una API REST propia
  en AWS: `https://prod.alsuperapi.com` (`rootUrl` del entorno de producción, en
  `chunk-WPKKTUZ6.js`). Existe también `https://api2.alsuper.com/v1` (nginx), que responde igual a
  las mismas rutas. Imágenes en `cdn.alsuper.com`.
- **Filtro por User-Agent, no WAF de huella TLS.** Sin impersonar y sin User-Agent, la API responde
  **403 `{"message":"Forbidden"}`** (5 de 5 en `validacion.csv`). Con un User-Agent de navegador
  responde 200 **aunque no se impersone** (lo mismo que hace el legado con `requests`). Con
  impersonación de Chrome, 200 (5 de 5, p50 0.59 s). No pide API key, cookies ni token.
- **Navegador:** por verificar (CAPTCHA). El bundle carga reCAPTCHA v3, pero solo para login y
  registro (`/auth/verify-recaptcha`).

### robots.txt

`www.alsuper.com/robots.txt`: `User-agent: *` prohíbe `/autenticacion`, `/carrito`, `/perfil`,
`/compra-en-proceso`, `/seguimiento`, `/pagos`, `/listas-alsuper`, `/webview-tyc`,
`/webview-aviso` y otras rutas de cuenta. **No prohíbe catálogo, búsqueda ni producto.** Sin
`Crawl-delay`. `Sitemap: https://www.alsuper.com/sitemap.xml`.

`prod.alsuperapi.com/robots.txt` responde 403 (no publica reglas).

### Términos de uso

**Por verificar en el navegador.** Están en `https://www.alsuper.com/nosotros/terminos`, pero la
página es una SPA y por HTTP solo llega el esqueleto. `/webview-tyc` (la versión para la app) está
prohibida en robots.txt.

## Sucursal

**El precio y el surtido dependen de la sucursal**, que va en la ruta: `/ms-products/branch/{id}`.

- `/stores?ecommerce=true` lista 54 sucursales en Chihuahua, Coahuila, Durango y Zacatecas, de las
  que 28 están activas en línea. La sucursal por defecto del sitio es la **6, Alsuper Plus Leones
  (Chihuahua capital)** (`defaultStore: "6"` en el entorno).
- **Precio:** en 5 sucursales de 5 plazas (Chihuahua 2, Saltillo 53, Torreón 54, Durango 75,
  Zacatecas 61) contra la 6, el `regular_price` coincide en todos los productos comunes de los
  primeros 100 de Farmacia. La única diferencia fue una oferta en Saltillo (34.90 → 23.90). Las
  ofertas sí pueden ser locales.
- **Surtido en línea:** 1,619 productos en la 6 contra 1,378 / 1,507 / 1,464 / 1,389 / 1,480.
- **El legado es la sucursal 6:** de los 100 primeros productos de Farmacia, los 100 están en el
  CSV de septiembre con los mismos precios, ofertas incluidas.
- **Propuesta:** fijar la sucursal 6 (`zona_precio = sucursal_6`), por continuidad con el legado y
  porque es la que muestra el sitio sin dirección. Capturar más plazas multiplica las peticiones
  por sucursal y solo aporta ofertas locales. **Decisión de Aldo.**

## Categorías y paginación

Departamentos en `/departments/web?branch=6` (17). **Farmacia es el 18**; el filtro usa el slug del
frontend, `department=farmacia-18` (`department=18` responde 404). Bebés es `bebés-15`, con acento.

Farmacia, sucursal 6 (2026-10-15):

| Categoría | En línea (`ecommerce=true`) | Todo el surtido |
| --- | --- | --- |
| Medicamentos de patente | 484 | 778 |
| Vitaminas y suplementos | 492 | 743 |
| Medicamentos | 389 | 509 |
| Curación y Rehabilitación | 155 | 304 |
| Salud Sexual | 45 | 82 |
| Incontinencia | 54 | 88 |
| **Total** | **1,619** | **2,504** |

- **`ecommerce=true` filtra a lo que se vende en línea.** Sin ese parámetro salen 2,504: 885
  productos más que se venden solo en tienda, todos con precio y EAN. El legado no mandaba
  `ecommerce`, así que capturaba el surtido completo.
- **Productos sin departamento:** los medicamentos de disfunción eréctil (Viagra, Cialis,
  sildenafil, tadalafil y similares) tienen `department = "No existe departamento"` y no aparecen
  al filtrar por Farmacia. Solo se alcanzan por palabra clave (`keyword=sildenafil` trae 10). El
  legado tenía 31 de estos.
- La respuesta trae facetas de categoría, subcategoría, marca y promoción con su conteo.

### Paginación y tope

- `page` (base 1) y `limit`. **No hay tope práctico:** `limit=2000` devolvió los 1,619 en una sola
  respuesta y `limit=3000` los 2,504 (4.3 MB). Después de la última página responde **404** con
  `{"data":[]}`.
- `total_items` trae el total de la búsqueda.
- **Anuncios:** no se vieron; los 2,504 `id` son únicos.

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0).**

`GET https://prod.alsuperapi.com/ms-products/branch/6?department=farmacia-18&page=N&limit=500`
con un User-Agent de navegador.

| Dato | Ruta en el JSON |
| --- | --- |
| SKU (= SKU del legado) | `data.data[].id` (= `sku` = `objectID`) |
| EAN | `data.data[].ean` (presente en los 2,504) |
| Nombre | `data.data[].name` |
| Marca | `data.data[].brand` |
| Presentación | `data.data[].format` |
| Categoría, subcategoría | `category_name`, `subcategory_name` |
| URL de la ficha | `share_url` |
| Imagen | `image_url` |
| **Precio de lista** | `regular_price` |
| **Precio de venta** | `price` (≤ `regular_price`; menor en 43 de 100) |
| Precio de club | `club_price` (0 en todos los observados) |
| Oferta | `promotion`, `fecha_inicio_oferta`, `fecha_fin_oferta` |
| Existencia en la sucursal | `stock` |
| Se vende en línea | `ecommerce` |

Muestra con 2 productos y las facetas en `muestras/ms_products_farmacia_2.json`. Sin firma ni
token. El legado guarda `Precio_Actual = regular_price` y `Precio_Oferta = price`.

La ficha (`/products/{id}/branch/{sucursal}`) existe, pero no hace falta.

### Cobertura del legado

El CSV de septiembre tiene 2,057 filas: 1,446 de Farmacia, 580 de **Bebés** (pañales, papillas,
ropa) y 31 de disfunción eréctil sin departamento. Es decir, el legado recorría también Bebés. De
Farmacia le faltaban 1,058 de los 2,504.

## Propuesta

### Escalón elegido: a, API JSON sin impersonar, con User-Agent de navegador (f = 0)

La API responde a HTTP simple siempre que lleve un User-Agent de navegador. Impersonar también
funciona y cuesta poco: el spider puede usar curl_cffi de todos modos para que el User-Agent y la
huella TLS sean coherentes.

### Estrategia de cobertura

1. Sucursal fija (6, salvo que Aldo decida otra cosa).
2. Por departamento del alcance (`farmacia-18` y, si el Excel de alcance lo incluye, `bebés-15`),
   **sin** `ecommerce=true`, con `limit=500` y `page` desde 1 hasta cubrir `total_items` o recibir
   404.
3. Lista de palabras clave para los productos sin departamento (`sildenafil`, `tadalafil`,
   `vardenafil`, `viagra`, `cialis`…), quedándose con los de `department = "No existe
   departamento"`.
4. Deduplicar por `id`.
5. **Cobertura por corrida:** únicos contra la suma de `total_items`.
6. **Ritmo:** 1 petición cada 2 s (C = 1). Las respuestas son grandes (unos 1.7 KB por producto),
   así que conviene `limit=500` y no una sola respuesta de 4 MB.

### Presupuesto (sección 5)

Supuestos: ipp = 500, f = 0, Z = 1, C = 1, L = 1.5 s (estimada para 500 productos), d = 2 s,
r = 0.05.

| Alcance | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Farmacia en línea | 1,619 | 4 | < 0.01 h | ✅ |
| Farmacia completa + sin departamento | ~2,535 | 6 + ~6 palabras | < 0.01 h | ✅ |
| Lo mismo + Bebés (= alcance del legado) | ~3,500 | ~14 | < 0.01 h | ✅ |
| Farmacia en las 28 sucursales en línea | ~2,500 × 28 | ~170 | ~0.2 h | ✅ |

Menos de un minuto con una sucursal.

### Riesgos

- **Términos de uso:** por verificar.
- **Sucursal:** el precio regular coincide entre plazas, pero las ofertas pueden ser locales. Fijar
  la 6 deja fuera esas ofertas.
- **Filtro por User-Agent:** hoy basta con un User-Agent de navegador. Si suben a un WAF con huella
  TLS, impersonar ya lo cubre.
- **Productos sin departamento:** dependen de una lista de palabras clave; un medicamento nuevo de
  esa clase con otro nombre no se capturaría.
- **Slugs de departamento** (`farmacia-18`, `bebés-15`): los arma el frontend con la descripción.
  Si cambian el nombre del departamento, cambia el slug; el spider debe leerlo de
  `/departments/web` en cada corrida.
- **Dos hosts** (`prod.alsuperapi.com` y `api2.alsuper.com/v1`): hoy responden igual; el sitio usa
  el primero.
