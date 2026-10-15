# Reconocimiento: Chedraui

- **URL:** https://www.chedraui.com.mx
- **Slug:** chedraui
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); Aldo con Claude in Chrome para
  segmento, selector de dirección, precio en pantalla y términos
- **Entorno:** solo oficina

Como en Guadalajara, casi todo se reconoció por HTTP: la API de búsqueda de VTEX responde sin
navegador ni impersonación. El navegador se usó solo para lo que no se ve por HTTP: el segmento de
la sesión, el selector de dirección, el precio visible con y sin dirección y los términos de uso
(unas 6 páginas, sin desafío).

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** VTEX IO. `window.__RUNTIME__` con `account = chedrauimx` y
  `workspace = master`; cookies `VtexWorkspace`, `VtexRCSessionIdv7`, `vtex-search-session`; imágenes
  en `chedrauimx.vteximg.com.br`.
- **WAF:** ninguno visible. Sin impersonar y con impersonación, 10 de 10 peticiones a la API
  respondieron 200 (p50 0.31 s y 0.35 s; `validacion.csv`). No hay cookies de Akamai, Cloudflare,
  HUMAN ni Imperva.
- **Navegador:** sin CAPTCHA ni pantalla de verificación en unas 6 páginas. Hay dos instancias de
  reCAPTCHA invisible (`.grecaptcha-badge`) que puntúan la sesión en segundo plano; no afectan a la
  API.
- **Cookies en el navegador** (solo nombres): `VtexWorkspace`, `__obref`, `vtex-search-session`,
  `vtex-search-anonymous`, `VtexRCSessionIdv7`, `VtexRCMacIdv7`, `transactionId`, `sp-variant`,
  más las de analítica (`_ga`, `_fbp`, `_ttp`, `_uetsid`, `TargetOne_*`, `_lr_*`, etc.). Al fijar
  dirección aparece `vtex_binding_address`; `vtex_segment` no es legible desde JS (HttpOnly).

### robots.txt

`User-agent: *` prohíbe `/search?*` y unas 70 rutas de categoría HTML, entre ellas `/Farmacia/`,
`/Higiene-y-Belleza/` y `/Super/`. **No prohíbe `/api/`.** Sin `Crawl-delay`. Una sola línea
`Sitemap: https://www.chedraui.com.mx/sitemap.xml` (índice de sitemaps por marca, producto,
etc.).

- **Riesgo informado:** las páginas HTML de Farmacia están prohibidas, pero el spider no las usa:
  solo consulta la API de Intelligent Search, que robots.txt no menciona.

### Términos de uso

`https://www.chedraui.com.mx/terminos-y-condiciones/plataformas-digitales` (actualizados el
2025-05-12). Ninguna cláusula menciona robots, scraping ni extracción automatizada. Lo más cercano:

- **2 (Licencia):** uso "exclusivamente para uso personal, no comercial"; prohíbe la
  "reimpresión, republicación, distribución, venta o reproducción electrónica" para otro uso, salvo
  autorización previa y por escrito de Chedraui.
- **3 (Uso del sitio):** prohíbe usar "dispositivo o software" para interferir con el uso correcto
  del sitio.
- **6 (Precio):** los precios varían por tienda; los publicados en el sitio pueden diferir de los
  de la tienda física.

**Riesgo escalado a Aldo** (decisión del 2026-10-15): igual que en Guadalajara, la cláusula 2
restringe el uso comercial. No bloquea el avance.

## Categorías y paginación

Farmacia es la categoría `4` (`category-1=farmacia`). Árbol y conteos de la faceta de Intelligent
Search (2026-10-15, sin región; muestra en `muestras/is_facets_farmacia_categorias.json`):

| Categoría (`category-2`) | Productos | Partición |
| --- | --- | --- |
| `medicamentos` | 3,384 | pasa el tope: por sus 11 `category-3` |
| `equipo-y-botiquin-medico` | 616 | directa |
| `vitaminas-y-suplementos` | 421 | directa |
| `salud-sexual` | 158 | directa |
| `incontinencia` | 99 | directa |
| `naturistas` | 78 | directa |
| `farmacia` | 2 | directa |
| **Total Farmacia** | **4,756** | |

Subcategorías de Medicamentos (suman exactamente 3,384): `diabeticos` 1,111, `estomacales` 569,
`analgesicos-y-anestesicos` 540, `dermatologicos` 376, `respiratorios` 299, `genericos` 268,
`oftalmicos-y-oticos` 142, `antimicoticos` 33, `naturistas-y-herbolarios` 29, `sueros-orales` 10,
`gripe-y-tos` 7.

La suma de las particiones da 4,758 contra 4,756: dos productos están en dos categorías y el spider
deduplica por `productId`. Ojo: las 43 `category-3` de toda Farmacia suman 4,750, así que **partir
solo por `category-3` pierde 6 productos** que no tienen subcategoría.

### Paginación y tope

- **Parámetros:** `count` (tamaño de página) y `page` (base 1). `count=50` y `count=100`
  devolvieron 50 y 100.
- **Tope:** igual que `catalog_system`, 2,500 resultados por búsqueda. Con `count=50`, la página 50
  devuelve 50 y la 51 responde **400**. Por eso Medicamentos (3,384) se parte.
- `recordsFiltered` trae el total de la búsqueda; con él se calcula el número de páginas.
- **Anuncios:** no se vieron. En 50 productos de Medicamentos, los 50 `productId` son únicos y no
  hay campos de patrocinio.

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0).**

`GET /api/io/_v/api/intelligent-search/product_search/category-1/farmacia/category-2/{cat}[/category-3/{sub}]?count=50&page=N`

| Dato | Ruta en el JSON |
| --- | --- |
| ID (= SKU del legado) | `products[].productId` |
| Nombre | `products[].productName` |
| Marca | `products[].brand` |
| URL de la ficha | `products[].link` (relativa, `/{linkText}/p`) |
| Categorías | `products[].categories` (rutas de texto) y `categoriesIds` |
| EAN | `products[].items[0].ean` |
| Imagen | `products[].items[0].images[0].imageUrl` |
| Precio de venta | `products[].items[0].sellers[0].commertialOffer.Price` |
| Precio de lista | `…commertialOffer.ListPrice` (también `PriceWithoutDiscount`) |
| Disponibilidad | `…commertialOffer.AvailableQuantity` (10,000 en todos los observados) |

Muestra con 2 productos en `muestras/is_listado_medicamentos_2.json`. El legado guarda como SKU el
mismo `productId` (por ejemplo, `3023895`), así que el histórico empata sin migración. A diferencia
de Guadalajara, **sí hay EAN**, útil para el cruce con el catálogo NDF.

No hay firma ni token: la petición no lleva cookies ni headers especiales.

## Ficha de producto

No hace falta para la corrida (f = 0). El legado abría cada ficha con Selenium solo para sacar el
`productId` y luego llamaba a `api/catalog_system/pub/products/search?fq=productId:{id}`. El listado
de Intelligent Search ya trae todo eso.

### Sucursal o zona

- **Sin dirección no hay región:** el segmento (`__RUNTIME__.segmentToken`, decodificado) trae
  `regionId = null`, `channel = "1"`. El header dice "Agregar una Dirección".
- **Selector:** drawer "¿Dónde te entregaremos?" con pestañas "Enviar a" (dirección libre o
  geolocalización) y "Recoger en" (dirección y luego una tienda concreta). No pide CP por separado.
- **El precio cambia por región.** Mismos 50 medicamentos, sin región contra el `regionId` de 4
  CP (obtenido de `/api/checkout/pub/regions?country=MEX&postalCode=…`): cambia el precio en 14
  (01000 CDMX), 18 (91000 Xalapa), 19 (64000 Monterrey) y 18 (44100 Guadalajara). El surtido
  también cambia: 3,384 medicamentos sin región contra 2,849 / 2,543 / 1,296 / 1,630.
- **Verificado en pantalla:** Aspirina 40 tabletas $57.00 sin dirección y $55.00 con dirección en
  CP 01000; Electrolife Zero 625 ml $27.50 y $23.00. Coincide con la API en ambos casos.
- El `regionId` del navegador para esa dirección agrupa 3 tiendas (`chedrauimx0177`, `0232`,
  `0235`); el de `/api/checkout/pub/regions` para el mismo CP agrega tiendas de surtido nacional
  (`0551`…, `darkstore`). Los precios salen iguales.
- **Decisión de Aldo (2026-10-15): sin región** (`zona_precio = sin_region`). Es el precio genérico
  del canal 1, el mismo que captura el legado (Aspirina a $57 en su CSV de septiembre), así que la
  serie histórica sigue comparable. El precio con dirección suele ser igual o menor.

## Propuesta

### Escalón elegido: a, API JSON sin impersonar (f = 0)

- La API pública de Intelligent Search responde 200 sin cookies, sin impersonación y sin desafío,
  y el listado trae precio, precio de lista, EAN y categoría.
- Valida la base VTEX para Farmatodo, Klyns y Similares (ALD-145): el spider se parametriza por
  dominio y árbol de categorías.

### Estrategia de cobertura

1. `tiendas.yml` declara las particiones: cada `category-2` de Farmacia y, para las que pasen de
   2,500, sus `category-3`. Mejor aún, que el spider lo decida solo: pide la faceta, y si una
   categoría pasa del tope baja un nivel (hoy solo Medicamentos).
2. Por partición pide `count=50&page=1`, lee `recordsFiltered` y pagina hasta cubrirlo.
3. Deduplica por `productId`.
4. **Cobertura por corrida:** únicos contra el total de la faceta de `category-1=farmacia`
   (4,756 hoy).
5. **Ritmo:** sin WAF, pero sin abusar: 1 petición cada 2 s (C = 1).

### Presupuesto (sección 5)

Supuestos: ipp = 50, f = 0, Z = 1, C = 1, L = 0.35 s (medida), d = 2 s, r = 0.05.

| Alcance | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Medicamentos (= legado, ~3,389 filas/mes) | 3,384 | 73 | ~0.05 h | ✅ |
| Farmacia completa (7 categorías) | 4,756 | 104 | ~0.06 h | ✅ |

Unos 4 minutos para Farmacia completa, contra los 2 días de calendario del legado. El alcance final
lo fija el Excel de alcance (ALD-161).

### Riesgos

- **Términos, cláusula 2:** restringe el uso comercial. Escalado a Aldo.
- **robots.txt** prohíbe las páginas HTML de Farmacia; la API no está prohibida. Si Chedraui
  agrega `/api/` a robots.txt, hay que reevaluar.
- **Zona:** se captura sin región. El precio sin región es más alto que el de una tienda concreta
  en ~30% de los productos, y el surtido sin región es más amplio que el de cualquier tienda.
- **Tope de 2,500:** si una `category-2` distinta de Medicamentos lo pasa, el spider debe bajar de
  nivel (ver el punto 1 de la estrategia). Las `category-3` no cubren todo (6 productos sin ella).
- **reCAPTCHA invisible** en el sitio: no afecta a la API hoy.
