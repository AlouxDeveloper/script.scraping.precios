# Reconocimiento: Klyns

- **URL:** https://www.klyns.mx
- **Slug:** klyns
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); pendiente Aldo con Claude in Chrome
  para términos de uso y precio en pantalla
- **Entorno:** solo oficina

Igual que en Chedraui y Farmatodo, casi todo se reconoció por HTTP: las APIs de VTEX responden sin
navegador ni impersonación. Quedan por ver en el navegador los términos de uso (no hay ruta de
términos en el sitemap) y el precio visible contra la API.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** VTEX IO. `window.__RUNTIME__` con `account = farmaciasklyns` y
  `workspace = master`; imágenes en `farmaciasklyns.vtexassets.com`. El segmento por defecto trae
  `regionId = null` y `channel = "1"`.
- **WAF:** ninguno visible. Sin impersonar y con impersonación, 20 de 20 peticiones a las dos APIs
  respondieron 200 o 206 (`validacion.csv`). El home no deja cookies de Akamai, Cloudflare, HUMAN
  ni Imperva.
- **Navegador:** por verificar (CAPTCHA, reCAPTCHA invisible, cookies).

### robots.txt

El más permisivo de los tres VTEX. Un solo grupo `User-agent: *` que prohíbe `/img/*`,
`/account/*`, `/login/*`, `/checkout/*`, `/busca/*` y `/quick-view/*`. **No menciona `/api/` ni
query strings**, así que Intelligent Search y `catalog_system` están permitidas. Sin `Crawl-delay`.
`Sitemap: http://www.klyns.mx/sitemap.xml` (marcas, categorías, productos y rutas personalizadas).

### Términos de uso

**Por verificar en el navegador.** El sitemap de rutas personalizadas solo trae marcas, campañas,
blog y `/sucursales`; ninguna ruta de términos o aviso legal.

## Categorías y paginación

Como Farmatodo, la farmacia está repartida en varios departamentos de primer nivel. Conteos de
Intelligent Search (2026-10-15, sin región):

| Departamento (`category-1`) | ID | Productos | Partición |
| --- | --- | --- | --- |
| `medicamentos-de-patente` | 68 | 3,672 | pasa el tope: por sus 9 `category-2` |
| `medicamentos-genericos-y-otc` | 78 | 1,337 | directa |
| `dermatologia` | 50 | 1,297 | directa |
| `vitaminas-y-suplementos` | 53 | 518 | directa |
| `salud-sexual` | 51 | 511 | directa (sin subcategorías) |
| `equipo-y-botiquin` | 64 | 509 | directa |
| `incontinencia` | 52 | 58 | directa (sin subcategorías) |
| `cuidado-de-la-piel` | 93 | 0 | vacía |
| **Total** | | **7,902** | |
| Solo medicamentos (patente y genéricos) | | 5,009 | |

- **Sin traslape:** la consulta OR de los 8 departamentos devuelve 7,902, igual a la suma.
- **Patente por `category-2`** (suman exactamente 3,672, ninguna pasa el tope; muestra en
  `muestras/is_facets_patente_categorias.json`): antiácidos y estomacales 737, analgésicos y
  antiinflamatorios 727, cardiovascular 551, antiinfecciosos 395, otros 390, respiratorios 327,
  alivio del dolor 262, oftálmicos 189, hormonas 94. IDs en
  `/api/catalog_system/pub/category/tree/2` (69 a 77).
- **Dermatología:** 1,297 productos pero solo 9 tienen `category-2`; el resto cuelga directo del
  departamento. Si algún día pasa el tope, no se puede partir por subcategoría (habría que usar
  marca o rango de precio).
- El árbol trae también departamentos de súper (bebés, alimentos, hogar, cuidado personal) que
  quedan fuera.

### Paginación y tope

Igual que Farmatodo:

- **Intelligent Search:** `count` y `page`; la página 51 con `count=50` da 400 ("Page should not
  exceed 50 pages"). Tope 2,500.
- **catalog_system:** `_from` y `_to`, máximo 50 por página, `_from` hasta 2,500 (206 con
  `resources = 2500-2549/3674`). Tope 2,550.
- `catalog_system` cuenta 3,674 en Patente contra 3,672 de Intelligent Search: probablemente
  productos sin existencia que Intelligent Search oculta.
- **Anuncios:** no se vieron. 50 `productId` únicos, un solo `item` y un solo seller por producto,
  sin campos de patrocinio.

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0), en las dos APIs.**

`GET /api/catalog_system/pub/products/search?fq=C:/{depto}/[{cat}/]&_from=N&_to=N+49`
o `GET /api/io/_v/api/intelligent-search/product_search/category-1/{depto}[/category-2/{cat}]?count=50&page=N`

| Dato | Ruta en el JSON (igual en las dos APIs) |
| --- | --- |
| ID interno | `[].productId` (= `items[0].itemId`) |
| **SKU del legado (EAN)** | `[].items[0].ean` |
| RefId interno (`100…`, 9 dígitos) | `[].productReference` (= `referenceId` RefId) |
| Nombre | `[].productName` |
| Marca | `[].brand` |
| URL de la ficha | `[].link` |
| Categorías | `[].categories` y `categoriesIds` |
| Imagen | `[].items[0].images[0].imageUrl` |
| Precio de venta | `[].items[0].sellers[0].commertialOffer.Price` |
| Precio de lista | `…commertialOffer.ListPrice` |
| Disponibilidad | `…commertialOffer.AvailableQuantity` (10,000 en los 50 observados) |

Muestra con 2 productos en `muestras/is_listado_patente_2.json`. Sin firma ni token.

**Descuento permanente:** los 50 productos de Patente tienen `Price < ListPrice` (por ejemplo,
Autrin 745.65 → 484.67 en el legado). Es el modelo de precios de Klyns, no una promoción
puntual.

### Empate con el legado

- El legado lee el identificador de la ficha (`product-identifier__value`). En septiembre son 6,740
  filas con SKU único: **6,380 son EAN** (`items[0].ean`) y **360 son el RefId** (`100…`,
  `productReference`). Ejemplo: Lacteol Fort guardado como `100004872` aunque la API ya trae EAN
  `7501124103378`.
- De 50 productos de Patente, 39 están en el CSV de septiembre: los 39 empatan por EAN y por URL,
  y ninguno por `productReference`.
- El legado guarda `Precio_Actual = ListPrice` y `Precio_Oferta = Price`. En los 12 revisados,
  `ListPrice` coincide en todos y `Price` en 10 (los otros 2 bajaron desde septiembre).
- **Consecuencia:** el spider guarda `items[0].ean` como SKU y también `productReference`. Con las
  dos columnas, las 360 series del legado que usan el RefId se reconcilian sin perder historia.

## Ficha de producto

No hace falta (f = 0). El legado recorría las categorías con Selenium ("Mostrar más") y abría cada
ficha para leer nombre, identificador, precios e imagen; el listado ya trae todo eso.

### Sucursal o zona

**Klyns no regionaliza.** `/api/checkout/pub/regions` devuelve el **mismo** `regionId` y ningún
seller para los 5 CP probados (01000, 91000, 64000, 44100, 80000). Con ese `regionId`, el surtido
de Patente sigue en 3,672 y los 50 precios son idénticos a los de sin región. Se captura sin región
(`zona_precio = sin_region`); no hay nada que fijar.

## Propuesta

### Escalón elegido: a, API JSON sin impersonar (f = 0)

Las dos APIs responden sin cookies, sin impersonación y sin desafío (p50 0.40 s `catalog_system`,
0.63 s Intelligent Search), y robots.txt permite las dos.

### ¿Basta la configuración de la base VTEX?

**Sí, sin subclase.** Lo que cambia contra Chedraui es configuración: dominio, departamentos,
particiones y el campo de SKU (`items[0].ean`, con `productReference` como columna adicional). No
hay región, firma ni sesión. Funciona con cualquiera de las dos APIs, así que Klyns no condiciona
la decisión de la base que planteó Farmatodo (allí solo `catalog_system` está permitida).

**Implicación para la base:** el campo de SKU varía por tienda (`productId` en Chedraui,
`productReference` en Farmatodo, `items[0].ean` en Klyns). Debe ser un parámetro de
`tiendas.yml`, no algo fijo en el código.

### Estrategia de cobertura

1. `tiendas.yml` declara los departamentos y, para Patente, sus 9 `category-2`. Mejor que el spider
   baje de nivel solo al ver un total mayor al tope.
2. Por partición pide la primera página, lee el total y pagina hasta cubrirlo.
3. Deduplica por `productId`.
4. **Cobertura por corrida:** únicos contra la suma de totales de los departamentos del alcance.
5. **Ritmo:** sin WAF, pero sin abusar: 1 petición cada 2 s (C = 1).

### Presupuesto (sección 5)

Supuestos: ipp = 50, f = 0, Z = 1, C = 1, L = 0.5 s (medida), d = 2 s, r = 0.05.

| Alcance | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Patente | 3,672 | 77 | ~0.06 h | ✅ |
| Patente y genéricos | 5,009 | 104 | ~0.08 h | ✅ |
| Los 7 departamentos de salud con productos | 7,902 | 165 | ~0.12 h | ✅ |

Unos 7 minutos en el peor caso. El legado sacó 6,740 filas en septiembre, así que ya cubría casi
todos los departamentos de salud. El alcance final lo fija el Excel de alcance (ALD-161).

### Riesgos

- **Términos de uso:** por verificar.
- **SKU mixto en el legado:** 360 series usan el RefId. Sin la columna `productReference`, esas
  series se cortan.
- **Dermatología sin subcategorías:** 1,297 productos colgados directo del departamento. Hoy está
  lejos del tope; si crece, la partición tendría que ser por marca o precio.
- **Tope de 2,500:** solo Patente lo pasa hoy.
