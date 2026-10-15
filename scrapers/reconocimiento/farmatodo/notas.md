# Reconocimiento: Farmatodo

- **URL:** https://www.farmatodo.com.mx
- **Slug:** farmatodo
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); pendiente Aldo con Claude in Chrome
  para términos de uso y precio en pantalla
- **Entorno:** solo oficina

Igual que en Chedraui, casi todo se reconoció por HTTP: las APIs de VTEX responden sin navegador
ni impersonación. Quedan por ver en el navegador los términos de uso (el pie de página se pinta en
el cliente y no hay ruta de términos en el sitemap) y el precio visible contra la API.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** VTEX IO. `window.__RUNTIME__` con `account = gruporfp` y `workspace = master`;
  imágenes en `gruporfp.vtexassets.com`. El segmento por defecto trae `regionId = null` y
  `channel = "1"`, igual que Chedraui.
- **WAF:** ninguno visible. Sin impersonar y con impersonación, 20 de 20 peticiones a las dos APIs
  respondieron 200 o 206 (`validacion.csv`). El home no deja cookies de Akamai, Cloudflare, HUMAN
  ni Imperva.
- **Navegador:** por verificar (CAPTCHA, reCAPTCHA invisible, cookies).

### robots.txt

Es la diferencia importante contra Chedraui. Varios grupos `User-agent: *` (se combinan) con:

- `Disallow: /*?`, `Disallow: /*&` y `Disallow: /*%`: prohíben **cualquier URL con query string**,
  lo que incluye la API de Intelligent Search (`…/product_search/…?count=50&page=1`).
- `Allow: /api/catalog_system/pub/products/search?fq=*`: permite **explícitamente** la API de
  catálogo con filtro `fq`. Por la regla de la coincidencia más larga, esta gana sobre `/*?`.
- También permite `/_v/public/graphql/v1?*`, `/*?page=*` y `/api/sessions?items=*`.
- Prohíbe `/busca/`, `/buscapagina`, `/checkout`, `/coleccion/` y otras rutas HTML que el spider
  no usa. Las páginas de categoría sin query string están permitidas.
- Sin `Crawl-delay`. `Sitemap: https://www.farmatodo.com.mx/sitemap.xml` (índice por marca,
  categoría, producto y rutas personalizadas).

**Consecuencia:** el spider debe usar `catalog_system` y no Intelligent Search (ver Propuesta).

### Términos de uso

**Por verificar en el navegador.** `/terminos-y-condiciones` y `/terminos-condiciones` responden
200 pero son la página de búsqueda de VTEX (soft 404); el sitemap de rutas personalizadas no trae
términos (sí `/aviso-de-privacidad`, `/preguntas-frecuentes`, `/quienes-somos`).

## Categorías y paginación

A diferencia de Chedraui (una sola categoría Farmacia), Farmatodo reparte la farmacia en varios
departamentos de primer nivel. Conteos de Intelligent Search (2026-10-15, sin región):

| Departamento (`category-1`) | ID | Productos | Partición |
| --- | --- | --- | --- |
| `medicamentos` | 7 | 3,559 | pasa el tope: por sus 17 `category-2` |
| `genericos` | 81 | 848 | directa |
| `farmacia` (insumos, primeros auxilios) | 254 | 629 | directa |
| `dermocosmetica` | 366 | 447 | directa |
| `suplementos-y-vitaminicos` | 223 | 335 | directa |
| `diabetes` | 431 | 228 | directa |
| `especialidades` | 1 | 108 | directa |
| `dermatologia` | 208 | 13 | directa |
| **Total** | | **6,167** | |
| Solo medicinales (medicamentos, genéricos, diabetes, especialidades) | | 4,743 | |

- **Sin traslape:** la consulta OR de los 8 departamentos devuelve 6,167, igual a la suma. Cada
  producto vive en un solo departamento.
- **Medicamentos por `category-2`** (suman exactamente 3,559, ninguna pasa el tope; muestra en
  `muestras/is_facets_medicamentos_categorias.json`): cardiología 573, neurología 527,
  digestión y estomacales 522, respiratorios 466, dolor 463, antiinfecciosos 455,
  dermatología 193, salud visual y auditiva 109, endocrinología 91, urología 62,
  ginecología 44, sexualidad 33, sistema óseo 7, sistema articular 7, otras terapias 3,
  control metabólico 3, oncología 1. Los IDs de cada una están en
  `/api/catalog_system/pub/category/tree/3` (cardiología = 33, neurología = 66, etc.).
- El árbol trae también departamentos de súper (abarrotes, lácteos, limpieza) que quedan fuera.

### Paginación y tope

- **catalog_system:** `_from` y `_to` (base 0, inclusivos), máximo 50 por página (`_to` − `_from`
  > 49 da 400). El total viene en el header `resources` (`0-49/3559`) y la respuesta es 206.
  **Tope:** `_from` no puede pasar de 2,500 (400 "Parameter _from can't be greater than 2500"),
  así que llega a 2,550 resultados por consulta.
- **Intelligent Search:** `count` y `page`, igual que Chedraui; la página 51 con `count=50` da 400
  ("Page should not exceed 50 pages").
- **Anuncios:** no se vieron. 50 `productId` únicos en la primera página de Medicamentos, un solo
  `item` por producto y sin campos de patrocinio.

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0), en las dos APIs.**

Recomendado (permitido por robots.txt):

`GET /api/catalog_system/pub/products/search?fq=C:/{depto}/[{cat}/]&_from=N&_to=N+49`

| Dato | Ruta en el JSON (igual en las dos APIs) |
| --- | --- |
| ID interno | `[].productId` (= `items[0].itemId`) |
| **SKU del legado (EAN)** | `[].productReference` (= `items[0].ean` = `referenceId` RefId) |
| Nombre | `[].productName` |
| Marca | `[].brand` |
| URL de la ficha | `[].link` (Intelligent Search la da relativa) |
| Categorías | `[].categories` y `categoriesIds` |
| Imagen | `[].items[0].images[0].imageUrl` |
| Precio de venta | `[].items[0].sellers[0].commertialOffer.Price` |
| Precio de lista | `…commertialOffer.ListPrice` |
| Disponibilidad | `…commertialOffer.AvailableQuantity` (10,000 en los 50 observados) |

Muestra de Intelligent Search con 2 productos en `muestras/is_listado_medicamentos_2.json`.

**Empate con el legado:** el legado guarda como `SKU` el texto "Sku:" de la ficha, que es el EAN
(`productReference`), no el `productId` como en Chedraui. De 50 productos de Medicamentos, 25 están
en el CSV de septiembre y en los 25 la URL coincide con `link`. El legado guarda
`Precio_Actual = ListPrice` y `Precio_Oferta = Price`; coinciden en 15 de los 25, el resto cambió
de precio entre septiembre y hoy. El spider debe usar `productReference` como SKU para que la serie
empate sin migración.

No hay firma ni token: las peticiones no llevan cookies ni headers especiales.

## Ficha de producto

No hace falta (f = 0). El legado recorría las categorías con Selenium ("Mostrar más") y luego abría
cada ficha para leer nombre, "Sku:", precios e imagen; el listado de la API ya trae todo eso.

### Sucursal o zona

- `/api/checkout/pub/regions?country=MEX&postalCode={cp}` devuelve un `regionId` con **una sola
  tienda** por CP (01000 → `gruporfp00383` Magdalena, 91000 → `00246`, 64000 → `00423` Obispado,
  44100 → `00412` Fincero).
- **El precio no cambia por región.** Mismos 50 medicamentos sin región contra los 4 CP: 0 precios
  distintos entre los productos comunes. Las únicas 2 diferencias (Xalapa) son `Price = 0`, es
  decir, sin existencia en esa tienda.
- **El surtido sí cambia:** 3,559 medicamentos sin región contra 1,358 / 1,129 / 1,734 / 1,324.
- **Propuesta: sin región** (`zona_precio = sin_region`), igual que la decisión de Chedraui: mismo
  precio y surtido completo. El legado tampoco fijaba dirección.

## Propuesta

### Escalón elegido: a, API JSON sin impersonar (f = 0)

- `catalog_system` responde 206 sin cookies, sin impersonación y sin desafío (p50 0.47 s), y trae
  precio, precio de lista, EAN y categoría. Intelligent Search trae lo mismo pero robots.txt lo
  prohíbe por el query string.

### ¿Basta la configuración de la base VTEX?

**Sí, si la base VTEX soporta `catalog_system`.** Lo que cambia contra Chedraui es configuración:
dominio, departamentos de primer nivel, particiones y el campo de SKU (`productReference` en vez
de `productId`). Hay dos opciones para la base (decisión de Aldo):

1. **Base sobre `catalog_system` para todas las tiendas VTEX** (recomendada). Chedraui no prohíbe
   `/api/` y la API trae los mismos campos, así que una sola implementación sirve para las dos y
   Farmatodo queda solo con configuración. Tope práctico 2,550 contra 2,500, igual de partible.
2. **Base sobre Intelligent Search con la API como parámetro** (`api: catalog_system`). Dos rutas
   de código en la misma base; tampoco requiere subclase.

En ninguna hace falta subclase: no hay firma, sesión ni sucursal que fijar.

### Estrategia de cobertura

1. `tiendas.yml` declara los departamentos (`fq=C:/{id}/`) y, para los que pasen de 2,500, sus
   `category-2` (`fq=C:/7/{id}/`; hoy solo Medicamentos). Mejor que el spider lo decida solo con el
   header `resources` de la primera página.
2. Por partición pide `_from=0&_to=49`, lee el total de `resources` y pagina hasta cubrirlo.
3. Deduplica por `productId`.
4. **Cobertura por corrida:** únicos contra la suma de totales de los departamentos del alcance.
5. **Ritmo:** sin WAF, pero sin abusar: 1 petición cada 2 s (C = 1).

### Presupuesto (sección 5)

Supuestos: ipp = 50, f = 0, Z = 1, C = 1, L = 0.5 s (medida), d = 2 s, r = 0.05.

| Alcance | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Medicamentos | 3,559 | 82 | ~0.06 h | ✅ |
| Medicinales (+ genéricos, diabetes, especialidades) | 4,743 | 107 | ~0.08 h | ✅ |
| Los 8 departamentos de salud | 6,167 | 137 | ~0.10 h | ✅ |

Unos 6 minutos en el peor caso, contra los días de Selenium del legado (2,573 filas en septiembre).
El alcance final lo fija el Excel de alcance (ALD-161).

### Riesgos

- **robots.txt** prohíbe las URL con query string; solo `catalog_system?fq=` está permitido. Si la
  base VTEX usa Intelligent Search, Farmatodo queda fuera de robots.txt.
- **Términos de uso:** por verificar.
- **SKU distinto a Chedraui:** `productReference` (EAN). Si un producto no tiene `productReference`,
  hay que decidir el respaldo (`productId`); en los 50 observados siempre viene.
- **Tope de 2,550:** si un departamento distinto de Medicamentos lo pasa, el spider debe bajar de
  nivel.
- **Precio 0** marca falta de existencia cuando hay región; sin región no se observó, pero el spider
  debe descartar `Price = 0` en lugar de guardarlo como precio.
