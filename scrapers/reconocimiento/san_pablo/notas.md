# Reconocimiento: San Pablo

- **URL:** https://www.farmaciasanpablo.com.mx
- **Slug:** san_pablo
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); pendiente Aldo con Claude in Chrome
  para precio en pantalla y si el sitio pide CP
- **Entorno:** solo oficina

Se reconoció por HTTP, incluidos los términos de uso, que se leyeron de la API de contenido del
propio sitio. La API OCC sigue igual que en el legado y además tiene un endpoint de búsqueda por
categoría con precio, así que ya no hace falta pedir ficha por ficha.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** SAP Commerce Cloud con frontend Spartacus (SPA). La API OCC vive en otro host:
  `https://api.farmaciasanpablo.com.mx/rest/v2/fsp/`. La búsqueda está respaldada por Algolia
  (`algoliaSearch.algoliaIndex = PROD_Products` en la respuesta), pero se consume a través de OCC.
- **WAF: Akamai.** Sin impersonar, la API responde **403 "Access Denied"** (5 de 5, cuerpo de
  433 bytes de Akamai). Con impersonación de Chrome responde 200 (5 de 5, p50 0.26 s;
  `validacion.csv`). No hace falta mandar `Origin` ni `Referer`: el bloqueo es por huella TLS.
- **Formato:** sin `Accept: application/json`, OCC responde XML. El spider debe mandar ese header.
- **Navegador:** por verificar (CAPTCHA, cookies de Akamai).

### robots.txt

- `www.farmaciasanpablo.com.mx/robots.txt` (versión 2025.05.15): `User-agent: *` prohíbe
  `/*?`, `/api/`, `/cart/`, `/checkout/`, `/my-account/` y varias rutas de campañas. Sin
  `Crawl-delay`. Bloquea por completo a `YouDaoBot`.
- `api.farmaciasanpablo.com.mx/robots.txt` responde **404**: el host de la API no publica reglas.
- **Lectura:** las reglas de robots.txt aplican por host, así que la API no está prohibida
  formalmente. Pero el `Disallow: /api/` y `/*?` del sitio muestran la intención de no ser
  rastreado por API ni por búsqueda. **Riesgo informado.**

### Términos de uso

`https://www.farmaciasanpablo.com.mx/terminos-y-condiciones/generales`, leídos de
`/rest/v2/fsp/cms/pages?pageLabelOrId=/terminos-y-condiciones/generales`. No mencionan robots ni
scraping por nombre, pero son los más restrictivos de las tiendas revisadas hasta ahora:

- El sitio "sólo puede ser usado como un medio de información de bienes y productos ofrecidos al
  menudeo, para consumo personal". "Cualquier otro uso incluyendo la reproducción … se encuentra
  estrictamente prohibido".
- "Queda terminantemente prohibido copiar, publicar, transmitir … **descargar, almacenar**,
  reproducir … crear trabajos derivados de este contenido".
- Cada usuario acepta no "explotar para fines comerciales ninguna parte de este sitio".
- **3.3 Precio ofrecido:** el precio publicado es el de venta al público según el artículo 42 de
  la LFPC.

**Riesgo a escalar a Aldo**, igual que Chedraui y Guadalajara, pero con una prohibición más
explícita de descargar y almacenar contenido.

## Categorías y paginación

Códigos de categoría jerárquicos: 2 dígitos el departamento, 5 la categoría y 9 la subcategoría.
Conteos de la búsqueda OCC (2026-10-15):

| Departamento | Código | Productos |
| --- | --- | --- |
| Medicamentos | `06` | 5,419 |
| Cuidado personal y belleza | `03` | 1,825 |
| Dermocosméticos | `04` | 1,714 |
| San Pablo Natural | `07` | 1,635 |
| Bebés | `02` | 691 |
| Vitaminas y suplementos | `09` | 569 |
| Equipo y botiquín | `05` | 568 |
| Alimentos y bebidas | `01` | 167 |
| Salud sexual | `08` | 83 |
| **Sitio completo** (`NavigationRoot`) | | **12,652** |

Los departamentos suman 12,871: unos 220 productos están en más de un departamento. El spider
deduplica por `code`.

**Medicamentos (`06`) por categoría** (muestra en `muestras/occ_facetas_medicamentos.json`):

| Categoría | Código | Productos | Partición |
| --- | --- | --- | --- |
| Supervisión médica | `06011` | 3,107 | pasa el tope: por sus 9 subcategorías |
| Genéricos | `06006` | 746 | directa |
| Especialidades médicas | `06004` | 493 | directa |
| Estomacal | `06005` | 285 | directa |
| Gripe y tos | `06007` | 256 | directa |
| Dolor | `06003` | 181 | directa |
| Oftálmicos | `06008` | 147 | directa |
| Dermatológicos | `06002` | 126 | directa |
| `06001` | `06001` | 41 | directa |
| `06010` | `06010` | 23 | directa |

- Supervisión médica se parte por letra: `060110001` (A-B-C) 676, `…0002` (D-E-F) 543,
  `…0007` (S-T-U) 459, `…0005` (M-N-O) 346, `…0006` (P-Q-R) 320, `…0004` (J-K-L) 285,
  `…0003` (G-H-I) 238, `…0008` (V-W-X) 158, `…0009` (Y-Z) 82. Suman exactamente 3,107.
- Las 10 categorías suman 5,405 contra 5,419: **14 productos de Medicamentos no tienen
  categoría de 5 dígitos** y no se alcanzan partiendo por categoría.
- La faceta trae además códigos de campaña (`APEGO-001`, `TYPE-ZANTIBIOTIC`, `descuentos-20`…)
  que no son parte del árbol y deben ignorarse.

### Paginación y tope

- `GET /products/search?query=:relevance:category:{código}&pageSize=N&currentPage=P` (base 0).
- `pageSize` acepta al menos 200 (se probaron 20, 100 y 200).
- **Tope de 1,000 resultados por consulta** (el límite por defecto de Algolia): `totalPages` se
  recorta a `1000 / pageSize` (10 con 100, 5 con 200) y la página siguiente responde 200 con
  `totalResults = 0` y sin productos. **No da error**: el spider tiene que comparar lo recibido
  contra el total de la faceta para detectar el recorte.
- **Anuncios:** no se vieron. 100 `code` únicos en la primera página de `060110001`.

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0).**

`GET https://api.farmaciasanpablo.com.mx/rest/v2/fsp/products/search?query=:relevance:category:{código}&pageSize=100&currentPage=N&fields=DEFAULT&lang=es_MX&curr=MXN`
con `Accept: application/json` e impersonación de Chrome.

| Dato | Ruta en el JSON |
| --- | --- |
| SKU (= SKU del legado) | `products[].code` (18 dígitos con ceros a la izquierda) |
| Nombre | `products[].name` |
| Presentación | `products[].additionalDescription` |
| URL de la ficha | `products[].url` (relativa) |
| Categorías | `products[].categories` |
| Imagen | `products[].images` |
| **Precio de lista** | `products[].price.value` |
| **Precio de venta** | `products[].basePrice.value` (≤ `price` en los 100 observados) |
| Genérico, antibiótico | `isGeneric`; `antibiotic` solo con `fields=FULL` |

Muestra con 2 productos en `muestras/occ_busqueda_060110001_2.json`. Sin firma ni token.

- **Nombres engañosos:** en OCC `basePrice` es el precio con descuento y `price` el de lista. En 12
  de 100 productos difieren. La ficha (`/products/{code}`) devuelve los mismos dos valores que la
  búsqueda.
- **Empate con el legado:** el legado guarda `PRECIO_ACTUAL = price` y `PRECIO_OFERTA = basePrice`,
  y `SKU = code`. De 100 productos, 63 están en el CSV de septiembre y los 8 revisados empatan en
  SKU y en precios, salvo uno que entró en descuento después.
- **Cobertura del legado:** 5,588 filas en septiembre, pero solo 943 de Medicamentos (de 5,419). El
  legado recorría una lista fija de URLs; el spider por categoría multiplica la cobertura de
  medicamentos por más de cinco.
- `potentialPromotions` trae promociones de regalo (compra uno, llévate otro); no cambian el precio
  unitario y no se capturan.

## Ficha de producto

No hace falta (f = 0). El legado pedía `/products/{sku}` por cada URL de una lista; la búsqueda ya
trae precio, nombre e imagen.

### Sucursal o zona

**Por verificar en el navegador.** Ni la búsqueda ni la ficha reciben sucursal, CP ni sesión: el
precio sale igual sin cookies. Hipótesis: precio único nacional del sitio. Falta confirmar si el
sitio pide CP y si el precio en pantalla cambia con él.

## Propuesta

### Escalón elegido: b, API JSON con HTTP impersonado (f = 0)

- Akamai bloquea la API por huella TLS sin impersonar y la deja pasar con `impersonate="chrome"`,
  sin cookies ni navegador. Es el mismo escalón que usa el legado, ahora con la búsqueda en lugar
  de la ficha.
- No encaja en la base VTEX: necesita un spider propio (ALD-146).

### Estrategia de cobertura

1. Pedir la faceta del departamento y bajar de nivel en cada categoría que pase de 1,000 (hoy en
   Medicamentos solo `06011`). Ignorar los códigos que no sean numéricos.
2. Por partición, `pageSize=100` desde `currentPage=0` hasta `totalPages`.
3. **Los 14 sin categoría:** recorrer también `06` partido por rango de precio (la faceta `price`
   trae los rangos) y quedarse con los `code` que falten. Si algún rango pasa de 1,000, se acepta
   la pérdida y se reporta.
4. Deduplicar por `code`.
5. **Cobertura por corrida:** únicos contra `totalResults` del departamento.
6. **Ritmo:** Akamai ya mostró que vigila; 1 petición cada 2 s (C = 1) y respetar el backoff de
   los middlewares ante 403 o 429.

### Presupuesto (sección 5)

Supuestos: ipp = 100, f = 0, Z = 1, C = 1, L = 0.3 s (medida), d = 2 s, r = 0.05.

| Alcance | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Medicamentos | 5,419 | ~62 (+ ~6 por precio) | ~0.04 h | ✅ |
| Sitio completo (9 departamentos) | 12,652 | ~140 | ~0.10 h | ✅ |

Unos 6 minutos el sitio completo, contra una petición por producto del legado (5,588 peticiones,
más de 2 horas con su `sleep(1)`). El alcance final lo fija el Excel de alcance (ALD-161).

### Riesgos

- **Términos de uso:** prohíben de forma explícita descargar, almacenar y reproducir el contenido
  y limitan el uso a consumo personal. Escalar a Aldo.
- **robots.txt:** el host de la API no publica reglas, pero el sitio prohíbe `/api/` y `/*?`.
- **Akamai:** hoy basta con impersonar. Si endurece (cookies `_abck`, sensor), habría que pasar al
  escalón d.
- **Tope silencioso de 1,000:** sin error; el spider debe vigilar la diferencia contra la faceta.
- **14 productos de Medicamentos sin categoría:** se recuperan por rango de precio, no por árbol.
- **Sucursal:** por verificar.
