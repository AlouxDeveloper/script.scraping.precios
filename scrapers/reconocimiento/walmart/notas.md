# Reconocimiento: Walmart México

- **URL:** https://www.walmart.com.mx
- **Slug:** walmart
- **Fecha:** 2026-10-06
- **Quién:** Aldo (con Claude in Chrome, extensión, desde Windows nativo); revisión de Claude Code
- **Entorno:** solo oficina

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`. El HAR sanitizado y
las capturas de los desafíos quedan locales en `salida/reconocimiento/walmart/` (fuera de git; no se
suben a GCS en este reconocimiento).

## Plataforma y protección

### Plataforma

**Next.js sobre un stack propio de Walmart**; no es ninguna de las plataformas comerciales de la
tabla 2.1 de la Metodología.

| Señal | Resultado |
| --- | --- |
| Next.js: `__NEXT_DATA__` | Presente. `page: "/"`, con claves `props`, `buildId`, `assetPrefix`, `runtimeConfig`, `locale`, `locales`, `defaultLocale` |
| Next.js: `/_next/static/` | Presente en el HTML |
| VTEX (`/api/catalog_system`, clases `vtex-`) | Ausente |
| Salesforce Commerce Cloud (`dwsid`, `demandware`) | Ausente |
| Magento (`/media/catalog/product`, `/static/version`) | Ausente |
| WooCommerce (`wp-content`) | Ausente |
| PrestaShop (`id_product`) | Ausente |
| SAP Commerce (`/rest/v2/`, `/occ/v2/`) | Ausente |
| Shopify (`cdn.shopify.com`) | Ausente |

Indicios de backend propio con GraphQL: `pageProps` incluye `persistedQueriesConfig`,
`enableGqlCsrRedirect`, `queryContextCacheId`, `initialTempoData`, `bootstrapData` e
`isomorphicSessionId`. No se observó ninguna petición GraphQL en red; es **hipótesis** por los
nombres de las claves.

Hosts en las peticiones de la portada: `i5-mx.walmartimages.com` (230 peticiones, imágenes),
`i5.walmartimages.com`, `b.wal.co`, `beacon.www.walmart.com.mx`, además de Google Tag Manager y
Google Ads. La extensión no pudo listar las rutas completas (su salida se bloquea cuando lleva query
strings); solo host y primer tramo de ruta.

### Protección

**HUMAN/PerimeterX y Akamai Bot Manager, ambos activos.**

- **HUMAN/PerimeterX, confirmado:**
  - Cookies `_px3`, `_pxvid`, `__pxvid`, `_pxde`, `pxcts`.
  - Red: `collector-pxaflyiz9n.px-cloud.net`, `ift.px-cloud.net` y la ruta propia
    `www.walmart.com.mx/px/...`.
  - Variable global `_pxAppId` definida en la página.
- **Akamai, coincide:** cookies `_abck` y `bm_sz`. `bm_sv` y `ak_bmsc`: no observadas.
- **Cloudflare** (`__cf_bm`, `cf_clearance`): no observadas.
- **Imperva/Incapsula:** sin páginas ni referencias en el HTML.
- **Cookies `TS…`:** el prefijo es el habitual de F5 BIG-IP; hipótesis por el nombre, no confirmada.

Nombres de cookies del dominio (solo las visibles desde JavaScript; las HttpOnly no se observaron):

`TS012b8e7c`, `TS014bbe1d`, `TS01782124`, `TS01fc8e13`, `TS9003c8fa027`, `__eoi`, `__gads`,
`__gpi`, `__pxvid`, `_abck`, `_astc`, `_ga`, `_ga_9K01KTJ6HC`, `_gcl_au`, `_intlbu`, `_px3`,
`_pxde`, `_pxvid`, `_shcc`, `adblocked`, `assortmentStoreId`, `bm_sz`, `bstc`, `exp-ck`, `hasACID`,
`hasLocData`, `mmuid`, `pxcts`, `userAppVersion`, `vtc`, `wmt.c`, `xpa`, `xpm`, `xptc`, `xpth`,
`xptwj`.

`assortmentStoreId` y `hasLocData` apuntan a que la sucursal se fija por cookie (a confirmar en P4).

**Desafío en la primera carga.** Con un perfil de Chrome limpio, la portada mostró el desafío
"¿Robot o humano? / Pulsar y mantener pulsado" de HUMAN/PerimeterX. Lo resolvió una persona y la
sesión continuó, por decisión de Aldo (la Metodología dice detenerse). Todo lo observado de aquí en
adelante corresponde a una sesión con `_px3` validada por un humano: **no representa lo que vería un
scraper sin navegador**.

### robots.txt

Contenido completo observado (un solo bloque):

```text
User-agent: *

Disallow: /cart*
Disallow: /tu-cuenta*
Disallow: /checkout*
Disallow: /search*
Disallow: /wallet*
Disallow: /account*
Disallow: /thankyou*
Disallow: https://www-qa.walmart.com.mx/*
Allow: /search?*z=1

# Sitemap XML
Sitemap: https://www.walmart.com.mx/siteindex.xml
```

- **Riesgo informado:** `/search*` está en Disallow (única excepción `Allow: /search?*z=1`). La
  búsqueda por texto queda descartada como ruta de extracción.
- No hay Disallow sobre rutas de producto (`/ip/`) ni de categoría (`/browse/`, `/content/`).
- Sin `Crawl-delay`.
- Un solo sitemap: `https://www.walmart.com.mx/siteindex.xml` (379 sitemaps hijos medidos el
  2026-10-01).
- **ToS:** por verificar (enlace pendiente).

## Categorías y paginación

Alcance: árbol completo de nivel 2 y las 25 hojas de Medicamentos; conteo y paginación verificados
solo en Analgésicos. Sesión: 7 páginas de las ~30 permitidas.

### Árbol de categorías

Ruta de navegación: menú hamburguesa → Departamentos → "Farmacia y Cuidado de la Salud" (ID
`264536`).

Patrón de URL e identificadores:

- Nivel 1 y 2 (páginas de contenido): `/content/farmacia-y-cuidado-de-la-salud/{slug}/{id1}_{id2}`
- Nivel 3, hoja (listado de productos):
  `/browse/farmacia-y-cuidado-de-la-salud/{slug2}/{slug3}/{id1}_{id2}_{id3}`
- El identificador es la cadena de IDs numéricos separados por `_` al final de la URL. En los datos
  embebidos aparece como `cat_id` con prefijo `cat`: `cat264536_cat1310112_cat2410125`.

**Nivel 2** (16 entradas del menú; la URL va tras el prefijo
`/content/farmacia-y-cuidado-de-la-salud`, salvo la primera). La columna "¿Medicamento?" es
clasificación por nombre: solo se abrió Medicamentos y las hojas de las otras 15 no se observaron.

| Categoría | URL (tras el prefijo) | ID | ¿Medicamento? |
| --- | --- | --- | --- |
| Destacados Salud y Bienestar | `/browse/farmacia-y-cuidado-de-la-salud/destacados-farmacia-y-cuidado-de-la-salud/lo-mas-vendido-farmacia-y-cuidado-de-la-salud/264536_300056_300057` (URL completa) | `264536_300056_300057` | No (colección "lo más vendido") |
| Medicamentos | `/medicamentos/264536_1310112` | `264536_1310112` | Sí |
| Oftálmicos y óticos | `/oftalmicos-y-oticos/264536_264594` | `264536_264594` | Probable (no abierta) |
| Sueros y Orales | `/sueros-y-orales/264536_1520002` | `264536_1520002` | Probable (no abierta) |
| Diabetes | `/diabetes/264536_960017` | `264536_960017` | Mixto probable (no abierta) |
| Vitaminas y Suplementos | `/vitaminas-y-suplementos/264536_264549` | `264536_264549` | No (suplementos) |
| Nutrición deportiva | `/nutricion-deportiva/264536_1520006` | `264536_1520006` | No |
| Fajas y Control de Peso | `/fajas-y-control-de-peso/264536_264552` | `264536_264552` | No |
| Equipo Ortopédico | `/equipo-ortopedico/264536_264578` | `264536_264578` | No |
| Equipo Médico | `/equipo-medico/264536_264564` | `264536_264564` | No |
| Material de Curación | `/material-de-curacion/264536_970119` | `264536_970119` | No |
| Botiquines | `/botiquines/264536_265802` | `264536_265802` | No |
| Bienestar Sexual | `/bienestar-sexual/264536_264585` | `264536_264585` | No |
| Incontinencia | `/incontinencia/264536_264537` | `264536_264537` | No (higiene) |
| Higiene íntima e incontinencia | `/higiene-intima-e-incontinencia/264536_264543` | `264536_264543` | No (higiene) |
| Accesorios para farmacia | `/accesorios-para-farmacia-y-cuidado-de-la-salud/264536_2067466` | `264536_2067466` | No |

**Hojas de Medicamentos** (25). URL:
`/browse/farmacia-y-cuidado-de-la-salud/medicamentos/{slug}/264536_1310112_{id3}`. Todas cuentan
como medicamentos por pertenecer a esa rama. De la 12.ª en adelante no se capturó el nombre visible.
`medimart` parece marca propia y `u-v-w-x-y` un índice alfabético (hipótesis por el slug).

| Categoría hoja | slug | id3 |
| --- | --- | --- |
| Alta Especialidad | `alta-especialidad` | 120504 |
| Analgésicos | `analgesicos` | 2410125 |
| Anti-tabaco | `anti-tabaco` | 3200034 |
| Antidiarreicos | `antidiarreicos` | 120483 |
| Antigripales | `antigripales` | 2460013 |
| Antihistamínicos | `antihistaminicos` | 2470024 |
| Antiinflamatorios | `antiinflamatorios` | 2470001 |
| Antimicóticos | `antimicoticos` | 2470026 |
| Antiparasitarios | `antiparasitarios` | 120480 |
| Antiulcerantes | `antiulcerantes` | 120482 |
| Antiácidos | `antiacidos` | 120484 |
| no observado | `congestion-nasal` | 120514 |
| no observado | `digestivos` | 2410120 |
| no observado | `dolor` | 120493 |
| no observado | `dolor-de-garganta` | 2470027 |
| no observado | `dolor-y-malestar` | 3200039 |
| no observado | `hemorroides` | 120495 |
| no observado | `laxante` | 120481 |
| no observado | `medimart` | 120505 |
| no observado | `oftalmicos` | 2470028 |
| no observado | `otros-medicamentos` | 2470029 |
| no observado | `pastillas` | 120497 |
| no observado | `presion-arterial` | 2470030 |
| no observado | `tos` | 120513 |
| no observado | `u-v-w-x-y` | 120470 |

### Productos por categoría

| Categoría | Total reportado | Fuente |
| --- | --- | --- |
| Analgésicos (`264536_1310112_2410125`) | 82 | `__NEXT_DATA__` → `searchResult.aggregatedCount` e `itemStacks[0].meta.totalItemCount`; en pantalla aparece como "(82)" |
| Las otras 24 hojas de Medicamentos | no observado | — |
| Las otras 15 entradas de nivel 2 | no observado | — |

La página no muestra un texto "N resultados"; el total aparece entre paréntesis.

### Paginación

- **Tipo:** paginación numerada con enlaces (`<nav aria-label="paginación">`, "Página anterior" /
  "Página siguiente"). Sin "mostrar más" ni scroll infinito.
- **Parámetro:** `page`. Página 1: `/browse/.../264536_1310112_2410125` (los enlaces añaden
  `affinityOverride=default`). Página 2: misma ruta con `?page=2&affinityOverride=default`.
- **Tamaño de página:** `ps = 44` en `paginationV2.pageProperties`. No aparece en la URL; si se puede
  modificar por URL: no observado.
- **Otros parámetros en `pageProperties`:** `sort` (`best_match`), `stores` (un ID de tienda), `prg`
  (`desktop`), `pageType` (`BrowsePage`), `grid`, `affinityOverride`, `cat_id`.
- **Productos por página observados:** página 1 = 40 productos + 1 espacio publicitario
  (`AdPlaceholder`); página 2 = 42 tarjetas. Suman 82, consistente con el total.
- **Peticiones de red:** el paso a la página 2 fue navegación del lado del cliente (sin recargar el
  documento; `__NEXT_DATA__` siguió mostrando la página 1). La petición de datos que la alimenta: no
  observado (solo beacons y analítica). Se captura a mano en DevTools para P3.
- **Dependencia de tienda:** el listado va ligado a una tienda (`stores`) y a la ubicación del
  encabezado; conteos y precios pueden variar por código postal. Hipótesis; no se probó cambiando de
  ubicación.

### Última página y tope

- Última página de Analgésicos: 2 (`paginationV2.maxPage: 2`); en ella desaparece "Página
  siguiente".
- Fuera de rango (`?page=3`): no redirige ni devuelve lista vacía; muestra "No se pudo encontrar esta
  página. ¡Lo sentimos!". Los datos embebidos traen `page: 3`, `maxPage: 2`, total 82 y 0 productos.
  Sirve como condición de parada del spider.
- **Tope en categorías grandes:** no observado; Analgésicos solo tiene 2 páginas. Por verificar en
  una categoría grande.

### Protección observada durante P2

**Segundo desafío.** Las páginas `/content/` (portada, menú, Medicamentos) cargaron sin desafío. La
primera entrada a `/browse/` (unos 10 min después del primer desafío; 5.ª página de la sesión, 3.ª en
~2 min) mostró "Verifica tu identidad / Mantén presionado". Lo resolvió una persona. Es consistente
con la vida de 5.5 min de `_px3` documentada por HUMAN, pero no se distingue si lo provocó la ruta
`/browse/` o el ritmo. La página 2 y `?page=3` cargaron después sin desafío. Captura:
`salida/reconocimiento/walmart/desafio_p2.png`.

### Pendiente

- Conteo de las otras 24 hojas de Medicamentos y de las demás ramas (después, con el spider o con una
  validación desde la oficina; no se gasta tráfico de reconocimiento en esto).
- Tope de paginación en una categoría grande (por ejemplo, Vitaminas y Suplementos).
- Petición de datos de la paginación y si `ps` se puede cambiar por URL.
- **Decisión de Aldo:** qué ramas de nivel 2 entran al alcance además de Medicamentos.

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí.** Los 78 productos observados en las dos
páginas de Analgésicos traen precio numérico y formateado en el JSON del listado; ninguno vino sin
precio. Cada página del listado es autosuficiente por URL (`?page=N` renderiza en servidor), así que
en el navegador no hace falta la llamada GraphQL.

### Campos por producto en `__NEXT_DATA__`

Ruta base: `props.pageProps.initialData.searchResult.itemStacks[0].items[n]`. Cada ítem trae
`__typename`; los productos son `"Product"` y hay un `"AdPlaceholder"` por página que hay que
filtrar. Muestra recortada en `muestras/listado_analgesicos_p1.json` (los ítems reales tienen unas 80
claves más).

| Dato | Ruta (relativa al ítem) | Ejemplo observado |
| --- | --- | --- |
| Precio actual (número) | `price` | `38` |
| Precio actual (texto) | `priceInfo.linePrice` | `"$38.00"` |
| Precio anterior / tachado | `priceInfo.wasPrice` | `""` si no hay; `"$68.00"` con descuento |
| Ahorro | `priceInfo.savings`, `priceInfo.savingsAmt` | `"Ahorra $7.00"`, `7` |
| ID / SKU | `usItemId` | `"00750164475124"` (parece EAN con ceros a la izquierda; hipótesis) |
| ID interno | `id` | `"1AB8FD0WHA8L"` |
| ID de oferta | `offerId` | hash de 32 caracteres |
| Nombre | `name` | `"Paracetamol Medimart 650 mg, 24 tabletas"` |
| URL canónica | `canonicalUrl` | `/ip/{slug}/{usItemId}` (relativa) |
| Imagen | `imageInfo.thumbnailUrl` | `https://i5-mx.walmartimages.com/asr/….jpeg` |
| Disponibilidad | `availabilityStatusV2.value` / `.display`, `isOutOfStock` | `"IN_STOCK"` / `"Disponible"`, `false` |
| Vendedor | `sellerName`, `sellerType`, `sellerId` | `"Walmart"`, `"INTERNAL"`, hash |
| Marca | `brand` | `null` en los 3 primeros |

Precio del JSON contra la tarjeta (3 primeros de la página 1): `00750164475124` 38 / $38.00,
`00750222742608` 45 / $45.00, `00750110976940` 62 / $62.00. Coinciden los tres.

`usItemId` es el mismo valor que el legado guarda como SKU (último tramo de la URL de la ficha), así
que el histórico empata sin migración.

### Casos especiales

| Caso | Página 1 (40) | Página 2 (38) | Cómo se distingue |
| --- | --- | --- | --- |
| Sin precio | 0 | 0 | `price` o `priceInfo.linePrice` vacíos |
| Precio "desde" o rango | 0 | 0 | `priceInfo.priceRangeString` no vacío o `priceInfo.minPrice > 0` (campos presentes, vacíos aquí) |
| Con variantes | 0 | no revisado | `variantCount > 0` |
| Con precio tachado | 4 | 6 | `priceInfo.wasPrice` no vacío |
| Vendedor externo (marketplace) | 1 | 5 | `sellerType: "EXTERNAL"` y `fulfillmentType: "MARKETPLACE"`; `sellerName` con el tercero (observado: "Farmacia Prixz") |
| Vendedor Walmart | 39 | 33 | `sellerType: "INTERNAL"`, `sellerName: "Walmart"` |
| Agotado | 0 | 0 | todos `IN_STOCK` |
| Patrocinado | 0 | no revisado | `sponsoredProduct` no nulo |

`catalogSellerId` no sirve para distinguir marketplace: vale `"1"` también en el ítem externo.

**Corrección a P2:** el JSON trae 40 + 38 = 78 productos, no los 82 de `aggregatedCount`; las 42
tarjetas contadas en la página 2 incluyen elementos fuera del listado principal. La causa de la
diferencia de 4: no observado. En la validación desde la oficina, la misma categoría reportó
`aggregatedCount: 76` (otra hora y la sucursal por defecto `stores: 3864`); el total varía y el
indicador de cobertura debe compararse contra el total de la misma corrida.

### Peticiones del navegador al paginar

Al pulsar "Página siguiente" (navegación del lado del cliente), excluyendo analítica, beacons, px e
imágenes:

| Método | Host | Ruta | Notas |
| --- | --- | --- | --- |
| GET | `www.walmart.com.mx` | `/orchestra/snb/graphql/Browse/{hash}/browse` | Trae los productos (deducido por tamaño, ~295 KB, y nombre de operación; el cuerpo no se leyó) |
| GET | `www.walmart.com.mx` | `/browse/.../264536_1310112_2410125` | Solo lleva el header `Synthetic-Request-For-Logging`, tamaño 0: registro, no datos |

- Es una **consulta GraphQL persistida**: el `{hash}` identifica la consulta y todo viaja en un único
  parámetro `variables` (JSON) con claves `page`, `ps`, `limit`, `catId`, `sort`, `prg`, `facet`,
  `min_price`, `max_price`, `seoPath`, `tenant`, `pageType` y decenas de banderas `enable…`/`fetch…`.
- En la carga inicial de la página 1 también hay un `POST /orchestra/graphql` (propósito no
  observado).
- **Firma o token:** ningún parámetro ni header con nombre de firma, token o autorización. Lo más
  parecido es el `{hash}`, que puede cambiar con cada despliegue (hipótesis).
- Headers que añade el código de la página: `x-o-segment`, `x-o-platform`, `x-o-platform-version`,
  `x-o-correlation-id`, `wm_qos.correlation_id`, `WM_MP`, `WM_CONSUMER.BANNER`, `WM_PAGE_URL`,
  `x-o-ccm`, `x-o-gql-query`, `X-APOLLO-OPERATION-NAME`, `x-o-bu`, `x-o-mart`, `x-o-vertical`,
  `tenant-id`, `traceparent`, `baggage`, `x-latency-trace`, `x-enable-server-timing`, `accept`,
  `accept-language`, `Content-Type`. Son de correlación, trazas y tenant. Los que agrega el
  navegador (cookies): no observado.
- En paralelo se dispara un `POST` a `b.px-cdn.net`: HUMAN evalúa la sesión en cada cambio de
  página.
- **Búsqueda por texto:** no se usa; `/search*` está en Disallow de robots.txt.

### Validación desde la oficina (sin navegador, curl_cffi)

Resultados en `validacion.csv` más 6 peticiones de inspección hechas a mano (2026-10-06, todas
impersonando Chrome y con pausas de 2 a 20 s):

| Petición | Sin impersonar | Impersonando Chrome |
| --- | --- | --- |
| Listado hoja, página 1 (sin query string) | 307 → `/blocked` | **200**, ~678 KB, p50 1.77 s; `__NEXT_DATA__` con 40 productos, los 40 con precio, iguales a los vistos en el navegador |
| Listado, `?page=2` (con y sin `affinityOverride`) | 307 → `/blocked` | **307 → `/blocked`**, también tras 20 s de pausa |
| Ficha `/ip/...` | 307 → `/blocked` | **307 → `/blocked`** |
| Listado página 1 de nuevo, después de los bloqueos | — | 200: el bloqueo es **por ruta, no por IP** |
| GraphQL persistido `Browse`, `page: 2`, con los headers `x-o-*` sin valores de sesión (ver P4) | — | **412** con JSON de bloqueo de HUMAN (`appId: PXAFlYiz9n`, `redirectUrl: /blocked…`, `blockScript: …/captcha/captcha.js`) |

La respuesta 200 de la página 1 trae `x-prerender-apache-hit: true` y
`cache-control: no-store`. **Hipótesis:** la página 1 de cada categoría la sirve un servicio de
prerender (el que se usa para buscadores), que no pasa por la evaluación de HUMAN; las URLs con query
string y las fichas llegan al origen y sin cookie `_px3` válida se redirigen a `/blocked`. No se ha
confirmado.

Consecuencia: **sin navegador solo se obtiene la página 1 (40 a 44 productos) de cada categoría
hoja.** Las páginas siguientes, las fichas y el GraphQL necesitan una sesión validada por HUMAN
(cookie `_px3`, que según HUMAN expira en 5.5 min).

### GraphQL persistido del listado (detalle)

`GET /orchestra/snb/graphql/Browse/{hash}/browse?variables={JSON}`

- **Hash** (2026-10-06): `366921d1ccb242eab27b0201ba47e5f0486b47a1121a6c77a2dad753b5f0e295`.
  Probablemente cambia con cada despliegue (hipótesis).
- **Variables:** las mismas claves que `pageProperties` (`page`, `ps: 44`, `limit: 40`, `catId`,
  `sort: best_match`, `prg: desktop`, `facet`, `min_price`, `max_price`, `tenant: WM_MEXICO`,
  `pageType: BrowsePage`), repetidas en los bloques `searchParams` y `fitmentSearchParams` (con
  `ps: 40`), más unas 50 banderas `enable…`/`fetch…`. **La sucursal no viaja en las variables.**
  La captura corresponde a `page: 1` (al volver con "Página anterior"); al ir a la 2, el cliente la
  sirvió de su caché sin petición nueva.
- **Headers propios con valor** (sin los de traza de sesión): `X-APOLLO-OPERATION-NAME: Browse`,
  `x-o-gql-query: query Browse`, `x-o-segment: oaoh`, `x-o-platform: rweb`,
  `x-o-platform-version: mxweb-1.235.0-…` (cambia con cada publicación), `x-o-ccm: server`,
  `x-o-bu: WALMART-MX`, `x-o-mart: B2C`, `x-o-vertical: EA`, `tenant-id: hvgqan`, `WM_MP: true`,
  `WM_CONSUMER.BANNER: GM`, `accept: application/json`, `accept-language: es-MX`.
- **Sin navegador:** 412 con bloqueo de HUMAN (tabla de validación de arriba). No es una ruta
  alternativa al escalón c.

## Ficha de producto

Ficha probada: `/ip/Paracetamol-Medimart-650-mg-24-tabletas/00750164475124`. En el navegador cargó
sin desafío; sin navegador, 307 a `/blocked` (ver Endpoints). Como el listado ya trae el precio
(f = 0), **la ficha no es necesaria para la corrida de precios**; sirve para enriquecer EAN y marca.

### Fuentes de datos

- `<script type="application/ld+json">`: 2 bloques (`Product` y `BreadcrumbList`).
- `__NEXT_DATA__`: página `/ip/[...itemParams]`; ruta base `props.pageProps.initialData.data`, con
  claves `product`, `idml`, `reviews`, `seoItemMetaData`, `contentLayout`.

| Dato | JSON-LD (`Product`) | `__NEXT_DATA__` (`…data.`) | Valor |
| --- | --- | --- | --- |
| Precio actual | `offers[0].price` (+ `priceCurrency`) | `product.priceInfo.currentPrice.price` / `.priceString` / `.currencyUnit` | 38 / "$38.00" / MXN |
| Precio tachado | no observado | `product.priceInfo.wasPrice` | `null` (sin descuento) |
| Ahorro | — | `product.priceInfo.savings`, `.savingsAmount` | `null` |
| SKU / usItemId | `sku` | `product.usItemId` | `00750164475124` |
| ID interno | — | `product.id` | `1AB8FD0WHA8L` |
| EAN / UPC | `gtin13` | `product.upc` | `00750164475124` |
| Marca | `brand.name` | `product.brand` | Medimart |
| Disponibilidad | `offers[0].availability` | `product.availabilityStatus`, `product.availabilityStatusV2` | `schema.org/InStock` / `IN_STOCK`, "Disponible" |
| Vendedor | no observado | `product.sellerName`, `.sellerDisplayName`, `.sellerType` | Walmart, `INTERNAL` |
| Nombre | `name` | `product.name` | igual al del listado |
| Imagen | `image` | — | misma URL que en el listado |

**Precio:** 38 en el listado, en JSON-LD, en `__NEXT_DATA__` y $38.00 en pantalla. Coinciden.

- `usItemId`, `sku`, `gtin13` y `upc` son el mismo valor: el identificador del producto es el código
  de barras con ceros a la izquierda. Confirmado solo en este producto; si se generaliza, el listado
  ya trae el EAN vía `usItemId` (útil para el crosswalk por EAN de `transform/`).
- `product.sellerId` vale `"0"` en la ficha y es un hash en el listado: no usarlo para cruzar.
- `priceInfo` de la ficha trae además `basePrice`, `listPrice`, `comparisonPrice`, `unitPrice`,
  `priceRange`, `isPriceReduced`, `volumePriceTiers`, `taxInfo` (valores no revisados).

### Campos que solo trae la ficha

| Campo | Ruta | Observado |
| --- | --- | --- |
| EAN/UPC explícito | `product.upc`, JSON-LD `gtin13` | Sí (en el listado solo se infiere de `usItemId`) |
| Marca | `product.brand`, JSON-LD `brand.name` | Medimart (en el listado `brand` era `null`) |
| Tipo de producto | `product.type` | "Prescription Medicines" |
| Ruta de categoría | `product.category.path[].name` | Farmacia y Cuidado de la Salud → Medicamentos |
| Descripción corta | `product.shortDescription`, `idml.shortDescription` | 658 caracteres |
| Descripción larga | `idml.longDescription`, JSON-LD `description` | 105 y 783 caracteres |
| Especificaciones | `idml.specifications[]` (`name`, `value`) | Solo 2: "Marca" y "Tipo de Batería" |
| Reseñas | `reviews`, JSON-LD `aggregateRating` | 5 de 5, 4 reseñas |
| Política de devolución | JSON-LD `offers[0].hasMerchantReturnPolicy` | Sin devolución |
| Laboratorio / fabricante | `product.manufacturerName` | No existe |
| Sustancia activa | `idml.ingredients` | `null` |
| Advertencias | `idml.warnings` | `null` |
| Guía de medicamento | `idml.drugGuide` | la clave existe; contenido no revisado |

Laboratorio, sustancia activa y presentación no vienen como campos estructurados: solo están en el
nombre.

### Sucursal

- **Por defecto en el encabezado:** "Miguel Hidalgo, 11220 • SC TOREO" (no se cambió).
- **Cookies de ubicación:** `assortmentStoreId = 2344`, `hasLocData = 1`. No hay otras visibles con
  "store" o "zip"; las HttpOnly no se pueden leer desde la página.
- `pageProperties.stores = 2344 = assortmentStoreId`: **la sucursal se fija por la cookie
  `assortmentStoreId`**, no por URL ni por las variables del GraphQL.
- **Sin cookie** (validación desde la oficina), el listado salió con `stores: 3864`: el sitio asigna
  otra sucursal por defecto (probablemente por IP o por la falta de `hasLocData`; hipótesis). Para
  una sucursal fija, el spider debe mandar `assortmentStoreId` explícita. Qué valores acepta y si
  basta con esa cookie: no observado.

### Protección durante P4

**Tercer desafío**, de página completa, al abrir el listado (paso A1); lo resolvió una persona.
Después, 2 cambios de página por clic, 1 "atrás" y 2 fichas sin desafío. Hasta aquí, tres desafíos
en tres sesiones: en la primera carga con perfil limpio (P1), en la primera entrada a `/browse/`
unos 10 min después (P2) y al reabrir el listado al inicio de P4. En cada caso, la navegación que
siguió en los minutos inmediatos ya no recibió desafío.

## Verificación de dudas

Sesión P5a (25 páginas) para cerrar lo que la Propuesta necesitaba: árbol completo, total, tope de
paginación, tamaño de página y EAN.

### Árbol de categorías

- La portada no trae el árbol: el menú se carga bajo demanda y solo llega a nivel 2.
- **Fuente:** la faceta `type: "cat_id"` dentro de `allSortAndFilterFacets` de cada listado
  `/browse/`; cada valor trae `id`, `name`, `itemCount` y `baseSeoURL`. Está en
  `initialData.searchResult.modules.allSortAndFilterFacets` (nivel 1) o en
  `initialData.contentLayout.modules[n].configs.allSortAndFilterFacets` (nivel 2): hay que buscar en
  ambas. Cada listado trae solo un nivel hacia abajo.
- **Patrón:** `/browse/farmacia-y-cuidado-de-la-salud/{slug-rama}/{slug-hoja}/{ID}`, con ID de hoja
  `264536_{rama}_{hoja}`. Confirmado con URLs reales solo en Medicamentos; en el resto es el patrón
  esperado. Los listados `/browse/` existen en los tres niveles.
- El spider puede descubrir el árbol solo a partir de la faceta, así que en `tiendas.yml` basta con
  declarar las ramas; las hojas se descubren en cada corrida (no se congelan en config).

**Nivel 2** (16 ramas). Los conteos varían entre cargas: faceta del nivel 1 / listado propio.

| Rama | Slug | ID | Productos (faceta nivel 1) | Productos (listado propio) | maxPage | Hojas |
| --- | --- | --- | --- | --- | --- | --- |
| Equipo Ortopédico | `equipo-ortopedico` | `264536_264578` | 117,059 | 101,783 | 23 | 15 |
| Equipo Médico | `equipo-medico` | `264536_264564` | 81,205 | 74,163 | 23 | 14 |
| Accesorios para Farmacia y Cuidado de la salud | `accesorios-para-farmacia-y-cuidado-de-la-salud` | `264536_2067466` | 29,085 | 28,098 | 23 | 17 |
| Fajas y Control de Peso | `fajas-y-control-de-peso` | `264536_264552` | 14,733 | 13,705 | 23 | 5 |
| Oftálmicos y Óticos | `oftalmicos-y-oticos` | `264536_264594` | 9,164 | 8,368 | 23 | 8 |
| Material de Curación | `material-de-curacion` | `264536_970119` | 6,495 | 6,462 | 23 | 9 |
| Vitaminas y Suplementos | `vitaminas-y-suplementos` | `264536_264549` | 6,056 | 6,058 | 23 | 8 |
| Botiquines | `botiquines` | `264536_265802` | 5,247 | 5,144 | 23 | 5 |
| Incontinencia | `incontinencia` | `264536_264537` | 4,992 | 4,665 | 23 | 5 |
| Destacados Farmacia y Cuidado de la Salud | no observado | `264536_300056` | 3,842 | no observado | no observado | no observado |
| Diabetes | `diabetes` | `264536_960017` | 3,831 | 3,362 | 23 | 4 |
| Medicamentos | `medicamentos` | `264536_1310112` | 3,053 | 3,053 | 23 | 25 |
| Nutrición Deportiva | `nutricion-deportiva` | `264536_1520006` | 2,011 | 1,441 | 23 | 1 |
| Bienestar Sexual | `bienestar-sexual` | `264536_264585` | 719 | 698 | 16 | 6 |
| Higiene Íntima e Incontinencia | `higiene-intima-e-incontinencia` | `264536_264543` | 275 | 275 | 7 | 2 |
| Sueros y Orales | `sueros-y-orales` | `264536_1520002` | 158 | 158 | 4 | 3 |

**Hojas de Medicamentos** (`264536_1310112`), slugs confirmados:

| Hoja | Slug | ID hoja | Productos |
| --- | --- | --- | --- |
| Alta Especialidad | `alta-especialidad` | 120504 | 2,252 |
| Otros Medicamentos | `otros-medicamentos` | 2470029 | 2,109 |
| Antigripales | `antigripales` | 2460013 | 227 |
| Antimicóticos | `antimicoticos` | 2470026 | 221 |
| Medimart | `medimart` | 120505 | 212 |
| Oftálmicos | `oftalmicos` | 2470028 | 156 |
| Congestión Nasal | `congestion-nasal` | 120514 | 131 |
| U-V-W-X-Y | `u-v-w-x-y` | 120470 | 109 |
| Digestivos | `digestivos` | 2410120 | 106 |
| Antiulcerantes | `antiulcerantes` | 120482 | 97 |
| Antiinflamatorios | `antiinflamatorios` | 2470001 | 94 |
| Analgésicos | `analgesicos` | 2410125 | 82 |
| Dolor | `dolor` | 120493 | 73 |
| Anti-tabaco | `anti-tabaco` | 3200034 | 58 |
| Antidiarreicos | `antidiarreicos` | 120483 | 48 |
| Antiparasitarios | `antiparasitarios` | 120480 | 38 |
| Antiácidos | `antiacidos` | 120484 | 38 |
| Laxante | `laxante` | 120481 | 38 |
| Tos | `tos` | 120513 | 33 |
| Presión Arterial | `presion-arterial` | 2470030 | 21 |
| Antihistamínicos | `antihistaminicos` | 2470024 | 15 |
| Dolor y Malestar | `dolor-y-malestar` | 3200039 | 13 |
| Dolor de Garganta | `dolor-de-garganta` | 2470027 | 6 |
| Pastillas | `pastillas` | 120497 | 6 |
| Hemorroides | `hemorroides` | 120495 | 4 |

**Hojas del resto de ramas** (slug de hoja no observado):

| Rama | Hoja | ID hoja | Productos |
| --- | --- | --- | --- |
| Oftálmicos y Óticos | Lentes Oftálmicos Mujer | 264660 | 5,477 |
| Oftálmicos y Óticos | Lentes Oftálmicos Hombre | 264661 | 4,419 |
| Oftálmicos y Óticos | Lentes | 120510 | 3,106 |
| Oftálmicos y Óticos | Lentes de Contacto | 264597 | 1,841 |
| Oftálmicos y Óticos | Soluciones para Lentes de Contacto | 1520007 | 196 |
| Oftálmicos y Óticos | Gotas para ojos | 3200051 | 151 |
| Oftálmicos y Óticos | Oído | 1520009 | 133 |
| Oftálmicos y Óticos | Lentes para niños | 264659 | 131 |
| Sueros y Orales | Sueros | 120479 | 141 |
| Sueros y Orales | Sueros Líquidos | 1520001 | 71 |
| Sueros y Orales | Sueros Efervescentes | 1520005 | 49 |
| Diabetes | Medias y Calcetines | 960022 | 2,748 |
| Diabetes | Jeringas | 960021 | 705 |
| Diabetes | Tiras Reactivas y Lancetas | 960019 | 320 |
| Diabetes | Glucómetros | 960018 | 64 |
| Vitaminas y Suplementos | Proteínas y Suplementos | 264550 | 5,354 |
| Vitaminas y Suplementos | Suplementos Dietéticos | 264551 | 2,174 |
| Vitaminas y Suplementos | Vitaminas y Suplementos | 3200083 | 785 |
| Vitaminas y Suplementos | Vitaminas | 350098 | 621 |
| Vitaminas y Suplementos | Herbolarias y Naturistas | 960025 | 619 |
| Vitaminas y Suplementos | Multivitamínicos | 960024 | 585 |
| Vitaminas y Suplementos | Clorofilas | 120509 | 19 |
| Vitaminas y Suplementos | Otros Medicina y Suplementos | 264631 | 7 |
| Material de Curación | Banditas | 265961 | 3,912 |
| Material de Curación | Algodón | 860020 | 1,925 |
| Material de Curación | Hisopos | 860021 | 1,126 |
| Material de Curación | Cintas Kinesiológicas | 3200045 | 286 |
| Material de Curación | Material de Curación | 3200080 | 141 |
| Material de Curación | Soluciones Antisépticas | 3200044 | 33 |
| Material de Curación | Alcohol | 860019 | 25 |
| Material de Curación | Otros | 3200046 | 16 |
| Material de Curación | Pomadas Antisépticas | 860025 | 15 |
| Botiquines | Cubre Bocas y Caretas | 265962 | 3,599 |
| Botiquines | Jeringas | 265801 | 698 |
| Botiquines | Gasas y Vendas | 265963 | 631 |
| Botiquines | Gel Antibacterial | 265964 | 325 |
| Botiquines | Guantes y Cubrebocas | 3200041 | 8 |
| Fajas y Control de Peso | Fajas Ortopédicas | 264554 | 4,916 |
| Fajas y Control de Peso | Productos Terapéuticos | 264555 | 2,991 |
| Fajas y Control de Peso | Medias de Compresión | 264557 | 2,748 |
| Fajas y Control de Peso | Suplementos Dietéticos | 264551 | 2,175 |
| Fajas y Control de Peso | Básculas y Medidores de Grasa | 264553 | 1,912 |
| Incontinencia | Ropa Interior | 264539 | 2,976 |
| Incontinencia | Pañales para Adultos | 264548 | 2,116 |
| Incontinencia | Toallas Protectoras | 960035 | 2,019 |
| Incontinencia | Calzones Anatómicos | 264538 | 22 |
| Incontinencia | Toallas Húmedas | 960036 | 1 |
| Higiene Íntima e Incontinencia | Toallas y Copas Menstruales | 264544 | 273 |
| Higiene Íntima e Incontinencia | Predoblados | 3200036 | 2 |
| Nutrición Deportiva | Accesorios de Nutrición Deportiva | 1520013 | 2,011 |
| Bienestar Sexual | Lubricantes y Humectantes | 264589 | 316 |
| Bienestar Sexual | Accesorios para Bienestar Sexual | 960028 | 277 |
| Bienestar Sexual | Condones y Anticonceptivos | 264591 | 119 |
| Bienestar Sexual | Juguetes Sexuales | 0293155 | 34 |
| Bienestar Sexual | Pruebas de Embarazo y Ovulación | 960027 | 32 |
| Bienestar Sexual | Accesorios | 3200050 | 1 |
| Accesorios para Farmacia | Cuidado Personal | 3200069 | 13,549 |
| Accesorios para Farmacia | Cremas | 3200027 | 5,028 |
| Accesorios para Farmacia | Bucales | 3200015 | 3,225 |
| Accesorios para Farmacia | Accesorios de Nutrición Deportiva | 1520013 | 2,011 |
| Accesorios para Farmacia | Aceites y Cremas | 3200021 | 1,957 |
| Accesorios para Farmacia | Cuidado de la Piel | 3200017 | 1,898 |
| Accesorios para Farmacia | Desodorantes | 3200068 | 1,883 |
| Accesorios para Farmacia | Repelentes | 120486 | 1,464 |
| Accesorios para Farmacia | Polvos | 3200026 | 280 |
| Accesorios para Farmacia | Accesorios para Bienestar Sexual | 960028 | 277 |
| Accesorios para Farmacia | Quemaduras y Protectores | 120487 | 105 |
| Accesorios para Farmacia | Estomacales | 3200079 | 100 |
| Accesorios para Farmacia | Cuidado de los Labios | 120488 | 84 |
| Accesorios para Farmacia | Talcos | 3200067 | 82 |
| Accesorios para Farmacia | Antimicóticos Pies | 3200062 | 51 |
| Accesorios para Farmacia | Antimicóticos Uñas | 3200063 | 22 |
| Accesorios para Farmacia | Antipiojos | 3200019 | 4 |
| Equipo Ortopédico | Ortopedia y Rehabilitación | 264580 | 49,211 |
| Equipo Ortopédico | Accesorios | 3200065 | 30,801 |
| Equipo Ortopédico | Accesorios (segunda entrada, otro ID) | 3200061 | 30,796 |
| Equipo Ortopédico | Cuidado del Paciente y Aseo | 264582 | 28,266 |
| Equipo Ortopédico | Masajeadores | 960014 | 14,347 |
| Equipo Ortopédico | Plantillas | 3200064 | 11,483 |
| Equipo Ortopédico | Collarines y Férulas | 264584 | 9,809 |
| Equipo Ortopédico | Cuidado de los Pies | 3200077 | 5,966 |
| Equipo Ortopédico | Callos, Ampollas y Juanetes | 3200066 | 5,304 |
| Equipo Ortopédico | Cuidado Personal | 3200078 | 5,297 |
| Equipo Ortopédico | Fajas Ortopédicas | 264554 | 4,916 |
| Equipo Ortopédico | Bastones | 960012 | 4,006 |
| Equipo Ortopédico | Sillas de Ruedas | 264581 | 3,406 |
| Equipo Ortopédico | Andaderas | 264579 | 1,998 |
| Equipo Ortopédico | Muletas | 960013 | 1,178 |
| Equipo Médico | Equipos de Laboratorio | 264576 | 22,712 |
| Equipo Médico | Instrumental Médico | 264575 | 18,663 |
| Equipo Médico | Humidificadores y Vaporizadores | 264566 | 17,597 |
| Equipo Médico | Respiratorios | 3200082 | 14,838 |
| Equipo Médico | Ortopedia y Equipos de Medición | 3200081 | 11,337 |
| Equipo Médico | Equipo para tu Salud | 960016 | 10,051 |
| Equipo Médico | Oxígeno y Productos para Oxígenoterapia | 264568 | 964 |
| Equipo Médico | Termómetros | 264565 | 360 |
| Equipo Médico | Nebulizadores | 264570 | 142 |
| Equipo Médico | Equipos y Accesorios | 3200072 | 118 |
| Equipo Médico | Baumanómetros, Oxímetros y Pulsómetros | 264567 | 112 |
| Equipo Médico | Camas de Hospital y Colchones | 264569 | 107 |
| Equipo Médico | Monitores de Presión | 960015 | 84 |
| Equipo Médico | Cámaras de Bronceado y UV | 264577 | 19 |

Observaciones:

- 127 hojas en 15 ramas (25 en Medicamentos, 102 en las demás); faltan las de Destacados
  (`264536_300056`).
- **Hojas compartidas** entre ramas con el mismo ID: Fajas Ortopédicas (264554), Suplementos
  Dietéticos (264551), Accesorios de Nutrición Deportiva (1520013) y Accesorios para Bienestar Sexual
  (960028). El prefijo de rama de esos IDs no es fiable.
- **Productos repetidos entre hojas:** las 25 hojas de Medicamentos suman 6,187 contra 3,053 de la
  rama. El spider deduplica por `usItemId`.
- **Conteos aproximados e incoherentes:** Nutrición Deportiva reporta 2,011 en su única hoja y 1,441
  en la rama; la suma de las 16 ramas (287,925) supera el total del nivel 1.
- **Medicamentos o afines fuera de la rama Medicamentos** (por nombre, sin abrir las hojas): Gotas
  para ojos y Oído (Oftálmicos y Óticos); las tres de Sueros y Orales; Pomadas y Soluciones
  Antisépticas (Material de Curación); Antimicóticos Pies y Uñas, Antipiojos, Estomacales y
  Quemaduras y Protectores (Accesorios para Farmacia); Condones y Anticonceptivos (Bienestar Sexual).

### Total de productos

| Listado | aggregatedCount | maxPage |
| --- | --- | --- |
| Nivel 1: `/browse/farmacia-y-cuidado-de-la-salud/264536` | 236,625 → 239,694 → 239,962 (entre cargas) | 23 |
| Nivel 2: Medicamentos `/browse/farmacia-y-cuidado-de-la-salud/medicamentos/264536_1310112` | 3,053 | 23 |

Medicamentos es ≈1.3% de la rama Farmacia; el grueso es Equipo Ortopédico y Equipo Médico. El
legado capturó 29,697 filas en agosto de 2026 desde un Excel de categorías que no está en el repo.

### Tope de paginación

**Hay tope: 23 páginas declaradas, unos 920 a 1,000 productos por listado.**

| Medida (nivel 1) | Valor |
| --- | --- |
| aggregatedCount | 236,625 |
| Páginas teóricas, ⌈236,625 / 40⌉ | 5,916 |
| maxPage declarado | 23 |
| `?page=23` | 40 productos; sin "Página siguiente" |
| `?page=24` | también carga 40 productos (`page: 24`, `maxPage` sigue en 23); si son distintos de la 23: no observado |
| `?page=25` | no observado |
| `?page=26` | "Bad Request…" sin `__NEXT_DATA__` (error de rango, no bloqueo) |

- `maxPage` vale 23 en todo listado de más de ~920 productos; los menores declaran su número real
  (Bienestar Sexual 16, Higiene Íntima 7, Sueros 4).
- En una hoja chica (Analgésicos), una página de más devuelve "No se pudo encontrar esta página".
- **Hojas de Medicamentos sobre el tope:** Alta Especialidad (2,252) y Otros Medicamentos (2,109).
  Hay que partirlas con filtros (marca, precio, vendedor); cómo se comportan los filtros: no
  observado. Las otras 23 caben completas.

### Tamaño de página

`?ps=100` en Analgésicos bajó `ps` a 20 (20 productos, `maxPage` 5): el parámetro se lee de la URL
pero 100 no se respeta. **Máximo confirmado: 40 por página.** Otros valores: no observado.

### EAN

| Producto | Vendedor | usItemId | product.upc | gtin13 | ¿Iguales? |
| --- | --- | --- | --- | --- | --- |
| Analgésico Alli-triple Diclofenaco + Complejo B, 20 tabletas | Walmart / INTERNAL | 00065024005362 | 00065024005362 | 00065024005362 | Sí |
| Syncol 12 comprimidos | Farmacia Prixz / EXTERNAL | 00750107060070 | 00750107060070 | 00750107060070 | Sí |
| Antigripal Medimart, 12 cápsulas | Walmart / INTERNAL | 00750222742564 | 00750222742564 | 00750222742564 | Sí |
| Paracetamol Medimart 650 mg, 24 tabletas (P4) | Walmart / INTERNAL | 00750164475124 | 00750164475124 | 00750164475124 | Sí |

- En 4 de 4 fichas, incluida la de un vendedor externo, `usItemId` = `upc` = `gtin13` = `sku`. Son 14
  dígitos con ceros a la izquierda; sin ellos quedan 13 o 12 (EAN-13 o UPC-A; dígito verificador no
  validado). **El listado ya trae el EAN**, con la reserva de que la muestra es de una sola categoría.
- En la ficha del externo, `sellerName` es la razón social ("LOGISTICA PRIXZ") y `sellerDisplayName`
  el nombre comercial ("Farmacia Prixz"); en el listado, `sellerName` trae el comercial.
- El slug de la ficha es libre: `/ip/producto/00750107060070` carga el producto correcto.

### Protección durante P5a

**Tres desafíos en 25 páginas**, todos resueltos por una persona: Medicamentos nivel 2 (página 3),
ficha del vendedor externo (página 13) e Incontinencia (página 21). Aparecen cada 8 a 10 páginas,
en `/browse/` y en `/ip/`, con pausas de 8 a 17 s entre cargas. **Hipótesis:** el desafío lo
dispara el volumen acumulado por sesión (mismo `_pxvid`), no una ruta concreta. Es consistente con
el legado, que abre un Chrome nuevo por cada URL.

## Propuesta

### Escalón elegido: d, navegador completo, solo sobre listados (f = 0)

- **Por qué no a ni b:** sin navegador solo pasa la página 1 de cada listado (prerender). La página
  N, las fichas y el GraphQL dan 307 o 412 de HUMAN.
- **Por qué no c** (navegador para cookies + GraphQL por HTTP): `_px3` dura 5.5 min, el hash de la
  consulta persistida y `x-o-platform-version` cambian con cada despliegue, y los desafíos salen por
  volumen. Sería más rápido pero frágil, y d ya cabe en el presupuesto.
- **Por qué no híbrido b + d:** la página 1 sin navegador ahorra poco y duplica el código.
- **f = 0:** el `__NEXT_DATA__` del listado trae precio, precio tachado, `usItemId` (= EAN), nombre,
  URL, imagen, disponibilidad y vendedor. No se abren fichas.
- **Activa ALD-120** (handler de navegador).

### Estrategia de cobertura

1. `tiendas.yml` declara las ramas de nivel 2 en alcance (configurable); el spider descubre las hojas
   con la faceta `cat_id` en cada corrida.
2. Recorre cada hoja con `?page=1..maxPage` y para cuando la página fuera de rango no trae productos.
3. Si una hoja reporta más de ~900 productos (`maxPage` = 23), la parte con facetas (marca o rango
   de precio) hasta que cada segmento quede bajo el tope (sección 6 de la Metodología). Los filtros
   no se han observado: se diseñan en ALD-120/ALD-121.
4. Deduplica por `usItemId` y guarda las hojas de cada producto.
5. Cobertura por corrida: únicos capturados contra `aggregatedCount` de cada rama en la misma corrida
   (los totales se mueven entre cargas).
6. **Sucursal fija:** manda la cookie `assortmentStoreId` explícita (sin ella el sitio asigna la
   3864; la sesión del navegador mostró 2344, SC Toreo).
7. **Desafíos:** renueva el contexto del navegador cada ≤ 5 páginas, antes del umbral observado de
   8 a 10. Ante un desafío, no se resuelve: se descarta el contexto, se espera y se reintenta con uno
   nuevo; K desafíos seguidos cierran la corrida con `bloqueo_sostenido`.
   **Corregido en ALD-120:** renovar el contexto empeora los desafíos; ver "Validación en ALD-120".

### Presupuesto (sección 5), por alcance

Supuestos: ipp = 40, f = 0, Z = 1, C = 1, d = 5 s, r = 0.2. L = 15 s por página con navegador,
incluido el costo de abrir un contexto nuevo cada 5 páginas (**hipótesis**: se mide en ALD-120).
q = mín(C / L, 1 / d) = 1/15 req/s.

| Alcance en `tiendas.yml` | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Medicamentos (25 hojas; 2 segmentadas) | 3,053 únicos | ~167 | ~0.8 h | ✅ |
| Volumen del legado | ~29,700 | ~743 | ~3.7 h | ✅ |
| Las 16 ramas | ~237,000 | ≥ 5,916 más la segmentación | ≥ 30 h | ⚠️, cerca del límite de 36 h |

Las 16 ramas obligan además a segmentar decenas de hojas (Ortopedia y Rehabilitación: 49,211
productos ≈ 54 segmentos), y con un desafío cada 8 a 10 páginas el riesgo de cierre por bloqueo
sostenido crece con el volumen.

### Riesgos

- **HUMAN:** desafío por volumen de sesión. Es el riesgo principal; si Patchright no pasa sin
  desafío con contextos nuevos, el escalón d no es viable sin intervención humana (prohibida en el
  scraper). Se valida en ALD-120 antes de escribir el spider.
- **robots.txt:** `/search*` en Disallow (no se usa). `/browse/` e `/ip/` permitidos.
- **ToS:** por verificar.
- **Tope de paginación:** obliga a segmentar las hojas grandes con filtros aún no observados.
- **Sucursal:** depende de la cookie `assortmentStoreId`; qué valores acepta: no observado.
- **Contrato:** las rutas de `__NEXT_DATA__` pueden cambiar con un despliegue (`buildId`).

### Peticiones a validar en ALD-120

1. Página 1 y `?page=2` de Analgésicos con Patchright y contexto nuevo, sin desafío.
2. 20 páginas seguidas renovando el contexto cada 5: ¿aparece algún desafío?
3. Una hoja sobre el tope (Alta Especialidad) con un filtro de marca o de precio: ¿cómo viaja en la
   URL y respeta el tope?
4. La cookie `assortmentStoreId` fijada a mano cambia `pageProperties.stores`.

## Validación en ALD-120 (2026-10-07)

Sonda de Scrapy con el escalón d (`precios_scrapers/navegador.py`): Patchright con Google Chrome
real y ventana visible, desde la oficina (WSL2 con WSLg), delay de 5 s con jitter de 0.5. No se
resolvió ningún desafío.

| Prueba | Resultado |
| --- | --- |
| 1. Analgésicos p1 y `?page=2`, contexto nuevo | ✅ 41 y 32 productos, sin desafío |
| 2. Contexto renovado cada 5 páginas | ❌ el contexto nuevo recibe el desafío en su primera página ("Verifica tu identidad", `/blocked`); renovarlo en cada bloqueo encadenó 6 desafíos seguidos |
| 2b. Un solo contexto toda la corrida | ✅ 25 páginas seguidas (Analgésicos p1-p2 y Medicamentos p1-p23) sin desafío, dos veces; ~6 s por página |
| 3. Hoja sobre el tope con filtro | No probado; pasa a ALD-121 |
| 4. Cookie `assortmentStoreId` a mano | ❌ solo la primera página sale con 2344 |

- **Desafío de HUMAN:** lo dispara la sesión nueva, no el volumen. En un contexto que acaba de recibir
  el desafío, la siguiente página pasa sin resolver nada: el sensor corre en la página del desafío y
  deja `_px3`. Por eso el escalón d usa **un solo contexto por corrida** y lo descarta solo con 2
  bloqueos seguidos (`NAVEGADOR_BLOQUEOS_POR_CONTEXTO`). La hipótesis de "un desafío cada 8 a 10
  páginas" del reconocimiento venía de navegación humana con pausas de 8 a 17 s y no se reprodujo.
- **Presupuesto:** L ≈ 6 s por página (no 15). Solo Medicamentos (~167 páginas) ≈ 17 min.
- **Sucursal:** el JavaScript del sitio geolocaliza la IP (`selectionSource: IP_SNIFFED_BY_LS`; la
  oficina cae en SC Puebla Reforma, 3864) y escribe `assortmentStoreId`, `locDataV3` y
  `locGuestData` en el host `www.walmart.com.mx`. Reescribir `assortmentStoreId` antes de cada página
  no basta: el servidor responde 3864, así que decide con `locDataV3` (JSON en base64 con `nodeId`) u
  otra señal. Fijar la sucursal queda para ALD-121 (opciones: elegir tienda por la interfaz una vez
  por contexto, o escribir `locDataV3`/`locGuestData` coherentes con 2344).
- **Status:** con Patchright, scrapy-playwright no recibe la respuesta de la navegación ("returned
  None"): todas las páginas llegan con status 200 y sin headers. Los bloqueos se detectan por la URL
  final (`/blocked`) y por las firmas del cuerpo; no hubo falsos positivos de `_pxhd` ni `captcha` en
  las páginas buenas.
- **Errores del navegador:** cerrar la página con rutas en vuelo hacía fallar la siguiente
  (`TargetClosedError`, 3 de 25 páginas); se corrige con `unroute_all` antes de cerrar, y los
  errores de Patchright se reintentan con Backoff.
- **Windows nativo:** la descarga funciona igual; el proceso no terminaba en 1 de cada 3 corridas
  (loop de scrapy-playwright sin cerrar, ver `cerrar_loop_windows`). Corregido: 20 de 20. Sonda completa en Windows: 25 de 25 páginas, sin desafío, 167 s.
