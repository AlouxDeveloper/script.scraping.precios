# Reconocimiento: Farmacias Similares

- **URL:** https://www.farmaciasdesimilares.com
- **Slug:** similares
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); pendiente Aldo con Claude in Chrome
  para términos de uso y precio en pantalla
- **Entorno:** solo oficina

El caso más simple de las tiendas VTEX: catálogo chico (1,369 productos en todo el sitio), sin tope
que partir, sin región que fijar y con robots.txt permisivo. Quedan por ver en el navegador los
términos de uso y el precio visible contra la API.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** VTEX IO. `window.__RUNTIME__` con `account = farmaciassimilaresmx` y
  `workspace = master`; imágenes en `farmaciassimilaresmx.vtexassets.com`. El segmento por defecto
  trae `regionId = null` y `channel = "1"`.
- **WAF:** ninguno visible. Sin impersonar y con impersonación, 20 de 20 peticiones a las dos APIs
  respondieron 200 o 206 (`validacion.csv`). El home no deja cookies de Akamai, Cloudflare, HUMAN
  ni Imperva.
- **Navegador:** por verificar (CAPTCHA, reCAPTCHA invisible, cookies).

### robots.txt

Un solo grupo `User-agent: *` que prohíbe `/account/`, `/login/`, `/checkout/`, `/busca/`,
`/quick-view/`, `/espiar/` y `/buscapagina/`. **No menciona `/api/` ni query strings**: las dos
APIs están permitidas. Sin `Crawl-delay`.
`Sitemap: https://www.farmaciasdesimilares.com/sitemap.xml` (marcas, categorías, productos y
8 rutas personalizadas de campañas).

### Términos de uso

**Por verificar en el navegador.** El sitemap no trae ruta de términos, aviso legal ni privacidad.

## Categorías y paginación

El sitio entero tiene 1,369 productos (búsqueda vacía de Intelligent Search). Conteos por
departamento (2026-10-15, sin región):

| Departamento (`category-1`) | ID | Productos |
| --- | --- | --- |
| `medicamentos` | 29 | 621 |
| `suplementos-y-multivitaminicos` | 71 | 133 |
| `higiene-curacion-y-diagnostico` | 24 | 128 |
| `aparato-respiratorio` | 63 | 95 |
| `cuidado-de-la-piel-y-belleza` | 6 | 85 |
| `analgesia` | 8 | 79 |
| `funcionamiento-gastrointestinal` | 17 | 77 |
| `souvenirs` | 1 | 41 |
| `deportistas` | 7 | 26 |
| `bebes` | 5 | 24 |
| `salud-sexual` | 70 | 19 |
| `diabetes` | 13 | 17 |
| `rehidratantes` | 62 | 15 |
| `peso-y-metabolismo` | 379 | 9 |
| `inactivo` | 341 | 0 |
| **Total** | | **1,369** |
| Medicinales (medicamentos, analgesia, respiratorio, gastrointestinal) | | 872 |

- **Sin traslape:** la consulta OR de todos los departamentos devuelve 1,369, igual a la suma y al
  total del sitio.
- **Árbol con relleno:** casi cada categoría tiene una hija llamada `-` (por ejemplo,
  `/medicamentos/antibiotico/-`). No afecta al spider, que pide por departamento.
- Similares vende sobre todo su propia marca de genéricos, así que el catálogo de medicamentos es
  chico (621) comparado con Farmatodo o Klyns.

### Paginación y tope

- Mismo mecanismo que Chedraui (Intelligent Search, `count` y `page`) y Farmatodo
  (`catalog_system`, `_from` y `_to` con 50 por página). Los dos topes (2,500 y 2,550) no se
  probaron porque **ningún departamento, ni el sitio entero, llega a ellos**: no hace falta partir.
- **Anuncios:** no se vieron. 50 `productId` únicos, un solo `item` y un solo seller por producto,
  sin campos de patrocinio.

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0), en las dos APIs.**

`GET /api/io/_v/api/intelligent-search/product_search/category-1/{depto}?count=50&page=N`
o `GET /api/catalog_system/pub/products/search?fq=C:/{id}/&_from=N&_to=N+49`

| Dato | Ruta en el JSON (igual en las dos APIs) |
| --- | --- |
| ID interno | `[].productId` (= `items[0].itemId`) |
| **SKU del legado** | `[].productReference` (= `items[0].ean` = RefId) |
| Nombre | `[].productName` |
| Marca | `[].brand` |
| URL de la ficha | `[].link` |
| Categorías | `[].categories` y `categoriesIds` |
| Imagen | `[].items[0].images[0].imageUrl` |
| Precio de venta | `[].items[0].sellers[0].commertialOffer.Price` |
| Precio de lista | `…commertialOffer.ListPrice` |
| Disponibilidad | `…commertialOffer.AvailableQuantity` (10,000 en los 50 observados) |

Muestra con 2 productos en `muestras/is_listado_medicamentos_2.json`. Sin firma ni token.

- **No hay EAN real.** El campo `ean` repite el código interno de 1 a 4 dígitos (por ejemplo, `522`
  para Amoxicilina/Ácido clavulánico 875 mg). Para el cruce con el catálogo NDF, Similares solo
  aporta nombre y marca, no código de barras.
- **Sin descuentos:** `Price = ListPrice` en los 50 productos de la API y en las 1,113 filas del
  legado de septiembre.

### Empate con el legado

- El legado guarda como `SKU` el identificador de la ficha, que es `productReference` (1,113 filas
  con SKU único, de 1 a 4 dígitos salvo 2 de 7).
- De 50 productos de Medicamentos, 43 están en el CSV de septiembre y en los 10 revisados empatan
  SKU = `productReference` y los dos precios.
- El legado sacó 1,113 productos contra 1,369 del sitio: cubría casi todo el catálogo.

## Ficha de producto

No hace falta (f = 0). El legado abría cada ficha de una lista de URLs en Excel para leer nombre,
identificador, precios e imagen; el listado ya trae todo eso.

### Sucursal o zona

`/api/checkout/pub/regions` devuelve un `regionId` con varios sellers (`farmaciassimilaresmxswl10`
y otros), pero **ni el precio ni el surtido cambian**: con la región de 4 CP (01000, 91000, 64000,
44100) Medicamentos sigue en 621 y los 50 precios son idénticos a los de sin región. Se captura
sin región (`zona_precio = sin_region`).

## Propuesta

### Escalón elegido: a, API JSON sin impersonar (f = 0)

Las dos APIs responden sin cookies, sin impersonación y sin desafío (p50 0.30 s Intelligent
Search, 0.33 s `catalog_system`), y robots.txt permite las dos.

### ¿Basta la configuración de la base VTEX?

**Sí, sin subclase.** Lo que cambia contra Chedraui es configuración: dominio, departamentos y el
campo de SKU (`productReference`, igual que en Farmatodo). No hace falta partir ni fijar región.
Funciona con cualquiera de las dos APIs, así que no condiciona la decisión de la base que planteó
Farmatodo.

### Estrategia de cobertura

1. `tiendas.yml` declara los departamentos del alcance; sin particiones.
2. Por departamento pide la primera página, lee el total y pagina hasta cubrirlo.
3. Deduplica por `productId`.
4. **Cobertura por corrida:** únicos contra la suma de totales de los departamentos del alcance.
5. **Ritmo:** 1 petición cada 2 s (C = 1).

### Presupuesto (sección 5)

Supuestos: ipp = 50, f = 0, Z = 1, C = 1, L = 0.35 s (medida), d = 2 s, r = 0.05.

| Alcance | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Medicamentos | 621 | 13 | ~0.01 h | ✅ |
| Medicinales (4 departamentos) | 872 | 19 | ~0.01 h | ✅ |
| Sitio completo | 1,369 | 28 | ~0.02 h | ✅ |

Un minuto en el peor caso. El alcance final lo fija el Excel de alcance (ALD-161).

### Riesgos

- **Términos de uso:** por verificar.
- **Sin EAN:** el cruce con el catálogo NDF depende solo del nombre (el ER vectorial), sin el atajo
  de `ean_cruzado`.
- **Árbol con categorías `-`:** si algún día hay que partir por `category-2`, esas hojas de relleno
  aparecen como valores de faceta y deben ignorarse.
