# Reconocimiento: Farmacias Guadalajara

- **URL:** https://www.farmaciasguadalajara.com
- **Slug:** guadalajara
- **Fecha:** 2026-10-07
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); Aldo con Claude in Chrome para menú,
  zona y términos
- **Entorno:** solo oficina

A diferencia de Walmart, casi todo se reconoció por HTTP sin navegador, porque el escalón b ya
estaba verificado (2026-10-01). El navegador solo se usó para lo que no se ve por HTTP: árbol del
menú, zona de precios y términos de uso (3 páginas, sin desafío).

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`. La lista de 11,797
URLs de producto del sitemap queda local en `salida/reconocimiento/guadalajara/` (fuera de git).

## Plataforma y protección

- **Plataforma:** Salesforce Commerce Cloud (SFRA). Cookies `dwsid`, `dwanonymous_*`, `dwac_*`,
  `dw_dnt`, `sid`; controladores bajo `/on/demandware.store/Sites-fragua-Site/`; atributos
  `data-pid` en las tarjetas.
- **Akamai Bot Manager:** cookies `_abck`, `ak_bmsc`, `bm_sz`, `bm_sv`, `bm_mi` en los `Set-Cookie`
  (DNS `edgekey.net`, visto el 2026-10-01). Detrás responde `server: cloudflare` (probable CDN de
  SFCC; no confirmado).
- **Huella TLS:** sin impersonar, todas las peticiones reciben `curl: (92) HTTP/2 stream reset by
  server`; impersonando Chrome, 200. Es el caso "bloqueo por huella TLS" de la Metodología.
- **Límite por ritmo:** tras unas 12 peticiones impersonadas en ~40 s dentro de la misma sesión,
  Akamai devolvió el mismo reset aun impersonando. A los 90 s volvió a responder 200, con y sin
  cookies previas. Con 10 s entre peticiones no se repitió en 30 peticiones más.
- **Navegador:** 3 páginas a 10 s, sin desafío.
- Nombres de cookies en el navegador: `PIM-SESSION-ID`, `__cq_bc`, `__cq_dnt`, `__cq_seg`,
  `__cq_uuid`, `_abck`, `_clck`, `_clsk`, `_fbp`, `_ga`, `_ga_0TKQZY73XS`, `_ga_WXK095J7LT`,
  `_gcl_au`, `bm_sv`, `bm_sz`, `cqcid`, `cquid`, `dw_dnt`, `dwac_31da5b7286290fa3cac76ab7f4`,
  `dwanonymous_1eee9edb9b92660bf4187107d4f1a30c`, `sid`.

### robots.txt

```text
User-agent: *
Allow: /

User-agent: *
Disallow: /buscar/*
Disallow: /on/demandware.store/
Disallow: /account
Disallow: /checkout
Disallow: /cart
Disallow: /ProductDisplay
Disallow: /*-app.html
Disallow: /FGAddZoneAttributes
Disallow: /iniciar-sesion/
Disallow: /carrito/

Sitemap: https://www.farmaciasguadalajara.com/sitemap_index.xml
```

- **Riesgo informado:** `/on/demandware.store/` prohíbe el controlador `Search-UpdateGrid` que usa
  el botón "Más resultados". Se evita: la URL SEO de la categoría acepta los mismos parámetros
  `start` y `sz` y está permitida.
- `/buscar/*` prohibido (no se usa) y `/FGAddZoneAttributes` prohibido (selector de zona; no se usa).
- Sin `Crawl-delay`.

### Términos de uso

`https://www.farmaciasguadalajara.com/terminos-y-condiciones/`. Ninguna de sus 28 secciones menciona
uso automatizado, robots, scraping, crawling ni extracción de datos. Lo más cercano:

- **3.2:** "queda terminantemente prohibido el uso comercial de dicha información".
- **3.3:** prohíbe la reproducción "electrónica o por otro medio, parcial o total" para un uso
  distinto al personal no comercial, salvo autorización previa y por escrito de FRAGUA.
- **16:** protege como derecho de autor la "recopilación" y "compilación" del contenido.

**Riesgo informado, a escalar a Aldo** (sección 9 de la Metodología): si AXIOM tiene fin comercial,
las cláusulas 3.2 y 3.3 son las que conviene revisar con un abogado. No bloquea el avance.

## Categorías y paginación

### Inventario del sitemap

`sitemap_index.xml` → `sitemap_0.xml` (5,000 URLs), `sitemap_1.xml` (5,000) y `sitemap_2.xml`
(3,166), todos con `<lastmod>`. De 13,166 URLs, **11,797 son fichas de producto** (patrón
`/{categoria}/{subcategoria}/{slug}-{id}.html`, IDs únicos); las otras 1,369 son boletín, super,
blog, landings y dos controladores.

Primer tramo de las fichas: `medicina` 3,219, `higiene-y-belleza` 1,969, `alimentos` 1,679,
`circulatorio` 602, `vitaminas-y-suplementos-` 491, `hogar` 488, `bebes` 474, `dermatologia` 445,
`curaciones` 417, `bebidas` 387, `visual` 340, `diabetes-y-endocrinas` 331 y 22 tramos menores.
**La ruta de la ficha no sigue la del menú** (`/medicina/analgesicos/…` contra
`/farmacia/medicina/dolor/analgesicos`); la miga de pan sí.

Es un catálogo general de farmacia con supermercado (alimentos, hogar, mascotas). El legado capturó
9,427 filas en agosto de 2026 desde un Excel de URLs fuera del repo.

### Árbol del menú

- Tres raíces con id en el HTML del menú: `F1` Farmacia, `D1` Dermo y `S1` Super. El id codifica el
  nivel: `F1` → `F1A1` (nivel 2) → `F1A1B4` (nivel 3) → `F1A1B4C1` (nivel 4, Analgésicos).
- 382 categorías con id único (el menú está duplicado: 542 enlaces). Solo Medicina (`F1A1`) y varias
  ramas de Super tienen nivel 4. Dermo → Marcas (`D1A7`) usa el nombre de la marca como id.
- La raíz (`/farmacia`, `/dermo`, `/super`) responde 301 a una landing `.html`; también Diabetes,
  Vitaminas, Mascotas y Bebés apuntan en el menú a una landing (`/control-glucosa.html`,
  `/vitaminas-y-suplementos.html`, `/mascotas.html`, `/bebes.html`). **Sus rutas de nivel 2 sí
  funcionan como listado** (validado: `/farmacia/diabetes-y-endocrinas`,
  `/farmacia/vitaminas-y-suplementos-`, `/super/mascotas`, `/super/bebes`).
- Varias URLs terminan en guion (`vitaminas-y-suplementos-`, `lavanderia-`, `vinos-`); así vienen en
  el HTML.
- **El listado de nivel 2 incluye todo su subárbol** (`/farmacia/medicina` = 3,575 productos), así
  que `tiendas.yml` puede declarar solo categorías de nivel 2.

**Totales por categoría de nivel 2** ("N productos" del listado, 2026-10-07):

| Raíz | Categoría (ruta de listado) | id | Productos |
| --- | --- | --- | --- |
| Farmacia | `/farmacia/medicina` | F1A1 | 3,575 |
| Farmacia | `/farmacia/accesorios-medicos` | F1A2 | 112 |
| Farmacia | `/farmacia/obesidad` | F1A3 | 76 |
| Farmacia | `/farmacia/circulatorio` | F1A4 | 664 |
| Farmacia | `/farmacia/curaciones` | F1A5 | 460 |
| Farmacia | `/farmacia/diabetes-y-endocrinas` | F1A6 | 375 |
| Farmacia | `/farmacia/incontinencia` | F1A7 | 62 |
| Farmacia | `/farmacia/salud-sexual` | F1A8 | 134 |
| Farmacia | `/farmacia/sueros` | F1A9 | 131 |
| Farmacia | `/farmacia/visual` | F1A10 | 362 |
| Farmacia | `/farmacia/vitaminas-y-suplementos-` | F1A11 | 590 |
| Farmacia | `/farmacia/dermatologia` | F1A12 | 478 |
| Dermo | `/dermo/cuidado-facial` | D1A1 | 204 |
| Dermo | `/dermo/cuidado-corporal` | D1A2 | 38 |
| Dermo | `/dermo/cuidado-del-cabello` | D1A3 | 25 |
| Dermo | `/dermo/cuidado-especializado` | D1A4 | 21 |
| Dermo | `/dermo/proteccion-solar` | D1A5 | 92 |
| Dermo | `/dermo/tipo-de-piel` | D1A6 | 41 |
| Dermo | `/dermo/marcas` | D1A7 | 296 |
| Super | `/super/alimentos` | S1A1 | 2,035 |
| Super | `/super/bebidas` | S1A2 | 443 |
| Super | `/super/electronicos` | S1A3 | 48 |
| Super | `/super/higiene-y-belleza` | S1A4 | 2,451 |
| Super | `/super/hogar` | S1A5 | 684 |
| Super | `/super/jugueteria` | S1A6 | 54 |
| Super | `/super/mascotas` | S1A7 | 124 |
| Super | `/super/papeleria` | S1A8 | 59 |
| Super | `/super/bebes` | S1A9 | 537 |
| Ofertas | `/ofertas/pharmalife` | — | 650 |

Subtotales: Farmacia 7,019; Dermo 717 (Marcas se traslapa con el resto de Dermo); Super 6,435;
Pharmalife 650 (marca propia, se traslapa con Farmacia). La suma con traslapes (~14,800) supera las
11,797 fichas únicas del sitemap: el spider deduplica por `data-pid`.

**Hojas de Farmacia** (id y ruta de listado; las de Dermo y Super están en el menú y el spider no
las necesita, porque basta con el nivel 2):

| Nivel 2 | Nivel 3 | Nivel 4 | Ruta | id |
| --- | --- | --- | --- | --- |
| Medicina | Antibióticos | Antibióticos | `/farmacia/medicina/antibioticos/antibioticos` | F1A1B1C1 |
| Medicina | Antibióticos | Antibacterianos | `/farmacia/medicina/antibioticos/antibacterianos-` | F1A1B1C2 |
| Medicina | Hemorroides | Antihemorroides | `/farmacia/medicina/hemorroides/antihemorroides` | F1A1B2C1 |
| Medicina | Digestivo | Amebicidas y Tricomonicidas | `/farmacia/medicina/digestivo/amebicidas-y-tricomonicidas` | F1A1B3C1 |
| Medicina | Digestivo | Antiácidos y Antigástricos | `/farmacia/medicina/digestivo/antiacidos-y-antigastricos` | F1A1B3C2 |
| Medicina | Digestivo | Antidiarreicos | `/farmacia/medicina/digestivo/antidiarreicos` | F1A1B3C3 |
| Medicina | Digestivo | Antieméticos y Anticinéticos | `/farmacia/medicina/digestivo/antiemeticos-y-anticineticos` | F1A1B3C4 |
| Medicina | Digestivo | Antihelmíticos | `/farmacia/medicina/digestivo/antihelmiticos` | F1A1B3C5 |
| Medicina | Digestivo | Colagogos y Coleréticos | `/farmacia/medicina/digestivo/colagogos-y-colereticos` | F1A1B3C6 |
| Medicina | Digestivo | Enzimas Digestivas | `/farmacia/medicina/digestivo/enzimas-digestivas` | F1A1B3C7 |
| Medicina | Digestivo | Laxantes | `/farmacia/medicina/digestivo/laxantes` | F1A1B3C8 |
| Medicina | Dolor | Analgésicos | `/farmacia/medicina/dolor/analgesicos` | F1A1B4C1 |
| Medicina | Dolor | Anestésico | `/farmacia/medicina/dolor/anestesico` | F1A1B4C2 |
| Medicina | Dolor | Antiespasmódicos | `/farmacia/medicina/dolor/antiespasmodicos` | F1A1B4C3 |
| Medicina | Dolor | Antiinflamatorios | `/farmacia/medicina/dolor/antiinflamatorios` | F1A1B4C4 |
| Medicina | Dolor | Relajantes Musculares | `/farmacia/medicina/dolor/relajantes-musculares` | F1A1B4C5 |
| Medicina | Homeopatía | Homeopático | `/farmacia/medicina/homeopatia/homeopatico` | F1A1B5C1 |
| Medicina | Hormonal | Anticonceptivos Hormonales | `/farmacia/medicina/hormonal/anticonceptivos-hormonales` | F1A1B6C1 |
| Medicina | Hormonal | Hormonales | `/farmacia/medicina/hormonal/hormonales` | F1A1B6C2 |
| Medicina | Hormonal | Hormonas Corticoster | `/farmacia/medicina/hormonal/hormonas-corticoster` | F1A1B6C3 |
| Medicina | Hormonal | Hormonas Crecimiento | `/farmacia/medicina/hormonal/hormonas-crecimiento` | F1A1B6C4 |
| Medicina | Hormonal | Hormonas Sexuales | `/farmacia/medicina/hormonal/hormonas-sexuales` | F1A1B6C5 |
| Medicina | Inmunológico | Antipalúdicos | `/farmacia/medicina/inmunologico/antipaludicos` | F1A1B7C2 |
| Medicina | Inmunológico | Biológicos | `/farmacia/medicina/inmunologico/biologicos` | F1A1B7C3 |
| Medicina | Inmunológico | Citostáticos | `/farmacia/medicina/inmunologico/citostaticos` | F1A1B7C4 |
| Medicina | Sistema Nervioso | Anticonvulsivos | `/farmacia/medicina/sistema-nervioso/anticonvulsivos` | F1A1B8C1 |
| Medicina | Sistema Nervioso | Antiparkinsoniano | `/farmacia/medicina/sistema-nervioso/antiparkinsoniano` | F1A1B8C2 |
| Medicina | Sistema Nervioso | Neuroléptico | `/farmacia/medicina/sistema-nervioso/neuroleptico` | F1A1B8C4 |
| Medicina | Sistema Nervioso | Parasimpaticomimético | `/farmacia/medicina/sistema-nervioso/parasimpaticomimetico` | F1A1B8C5 |
| Medicina | Sistema Nervioso | Psicotrópicos | `/farmacia/medicina/sistema-nervioso/psicotropicos` | F1A1B8C6 |
| Medicina | Sistema Nervioso | Reactivadores Cerebrales | `/farmacia/medicina/sistema-nervioso/reactivadores-cerebrales` | F1A1B8C7 |
| Medicina | Sistema Nervioso | Sedantes e Hipnóticos | `/farmacia/medicina/sistema-nervioso/sedantes-e-hipnoticos` | F1A1B8C8 |
| Medicina | Óseo | Antiartríticos | `/farmacia/medicina/oseo/antiartriticos` | F1A1B9C1 |
| Medicina | Respiratorio | Antigripales | `/farmacia/medicina/respiratorio/antigripales` | F1A1B11C1 |
| Medicina | Respiratorio | Antihistamínicos | `/farmacia/medicina/respiratorio/antihistaminicos` | F1A1B11C2 |
| Medicina | Respiratorio | Broncodilatadores | `/farmacia/medicina/respiratorio/broncodilatadores` | F1A1B11C3 |
| Medicina | Respiratorio | Terapia Nicotínica | `/farmacia/medicina/respiratorio/terapia-nicotinica` | F1A1B11C4 |
| Medicina | Respiratorio | Vías Respiratorias | `/farmacia/medicina/respiratorio/vias-respiratorias` | F1A1B11C5 |
| Medicina | Urinario | Tratamiento Gota | `/farmacia/medicina/urinario/tratamiento-gota` | F1A1B12C1 |
| Medicina | Urinario | Uricosúrico | `/farmacia/medicina/urinario/uricosurico` | F1A1B12C2 |
| Medicina | Urinario | Urología | `/farmacia/medicina/urinario/urologia` | F1A1B12C3 |
| Medicina | Urinario | Vías Urinarias | `/farmacia/medicina/urinario/vias-urinarias` | F1A1B12C4 |
| Accesorios Médicos | Baumanómetros | — | `/farmacia/accesorios-medicos/baumanometros` | F1A2B1 |
| Accesorios Médicos | Nebulizadores | — | `/farmacia/accesorios-medicos/nebulizadores` | F1A2B2 |
| Accesorios Médicos | Ortopédicos | — | `/farmacia/accesorios-medicos/ortopedicos` | F1A2B3 |
| Accesorios Médicos | Termómetros | — | `/farmacia/accesorios-medicos/termometros` | F1A2B4 |
| Obesidad | Antiobesidad | — | `/farmacia/obesidad/antiobesidad` | F1A3B1 |
| Circulatorio | Antianémico | — | `/farmacia/circulatorio/antianemico` | F1A4B1 |
| Circulatorio | Anticoagulantes | — | `/farmacia/circulatorio/anticoagulantes` | F1A4B2 |
| Circulatorio | Anticolesterol | — | `/farmacia/circulatorio/anticolesterol` | F1A4B3 |
| Circulatorio | Cardiovasculares | — | `/farmacia/circulatorio/cardiovasculares` | F1A4B4 |
| Circulatorio | Hemostáticos | — | `/farmacia/circulatorio/hemostaticos` | F1A4B5 |
| Circulatorio | Lipotrópicos e Hipocolesterol | — | `/farmacia/circulatorio/lipotropicos-e-hipocolesterol` | F1A4B6 |
| Circulatorio | Tónicos Reconstituyentes | — | `/farmacia/circulatorio/tonicos-reconstituyentes` | F1A4B7 |
| Circulatorio | Vasoconstrictores | — | `/farmacia/circulatorio/vasoconstrictores` | F1A4B8 |
| Curaciones | Alcohol | — | `/farmacia/curaciones/alcohol` | F1A5B1 |
| Curaciones | Algodón y Gasas | — | `/farmacia/curaciones/algodon-y-gasas` | F1A5B2 |
| Curaciones | Antisépticos y Antibacterianos | — | `/farmacia/curaciones/antisepticos-y-antibacterianos` | F1A5B3 |
| Curaciones | Botiquín | — | `/farmacia/curaciones/botiquin` | F1A5B4 |
| Curaciones | Cintas y Parches Adhesivos | — | `/farmacia/curaciones/cintas-y-parches-adhesivos` | F1A5B5 |
| Curaciones | Jeringas y Agujas | — | `/farmacia/curaciones/jeringas-y-agujas` | F1A5B6 |
| Curaciones | Accesorios para Curación | — | `/farmacia/curaciones/accesorios-para-curacion` | F1A5B7 |
| Curaciones | Vendas Elásticas y Adheribles | — | `/farmacia/curaciones/vendas-elasticas-y-adheribles` | F1A5B8 |
| Curaciones | Venditas | — | `/farmacia/curaciones/venditas` | F1A5B9 |
| Diabetes y Endocrinas | Antidiabéticos | — | `/farmacia/diabetes-y-endocrinas/antidiabeticos` | F1A6B1 |
| Diabetes y Endocrinas | Diuréticos | — | `/farmacia/diabetes-y-endocrinas/diureticos` | F1A6B2 |
| Diabetes y Endocrinas | Tiroides | — | `/farmacia/diabetes-y-endocrinas/tiroides` | F1A6B3 |
| Incontinencia | Pañales | — | `/farmacia/incontinencia/pa%C3%B1ales` | F1A7B1 |
| Incontinencia | Predoblados | — | `/farmacia/incontinencia/predoblados` | F1A7B2 |
| Incontinencia | Protectores | — | `/farmacia/incontinencia/protectores` | F1A7B3 |
| Incontinencia | Ropa Interior | — | `/farmacia/incontinencia/ropa-interior` | F1A7B4 |
| Incontinencia | Toallas Húmedas | — | `/farmacia/incontinencia/toallas-humedas` | F1A7B5 |
| Incontinencia | Toallas Protectoras | — | `/farmacia/incontinencia/toallas-protectoras` | F1A7B6 |
| Salud Sexual | Anticonceptivos | — | `/farmacia/salud-sexual/anticonceptivos` | F1A8B1 |
| Salud Sexual | Cuidado Femenino | — | `/farmacia/salud-sexual/cuidado-femenino` | F1A8B2 |
| Salud Sexual | Lubricantes | — | `/farmacia/salud-sexual/lubricantes` | F1A8B3 |
| Salud Sexual | Preservativos | — | `/farmacia/salud-sexual/preservativos` | F1A8B4 |
| Salud Sexual | Pruebas de Embarazo | — | `/farmacia/salud-sexual/pruebas-de-embarazo` | F1A8B5 |
| Sueros | Hidratación Oral | — | `/farmacia/sueros/hidratacion-oral` | F1A9B1 |
| Sueros | Soluciones Intravenosas | — | `/farmacia/sueros/soluciones-intravenosas` | F1A9B2 |
| Visual | Oftalmología | — | `/farmacia/visual/oftalmologia` | F1A10B1 |
| Visual | Óptica | — | `/farmacia/visual/optica` | F1A10B2 |
| Vitaminas y Suplementos | Complementos Alimenticios | — | `/farmacia/vitaminas-y-suplementos-/complementos-alimenticios` | F1A11B1 |
| Vitaminas y Suplementos | Multivitaminas | — | `/farmacia/vitaminas-y-suplementos-/multivitaminas` | F1A11B2 |
| Vitaminas y Suplementos | Suplementos Alimenticios | — | `/farmacia/vitaminas-y-suplementos-/suplementos-alimenticios` | F1A11B3 |
| Dermatología | Anti VPH | — | `/farmacia/dermatologia/anti-vph` | F1A12B1 |
| Dermatología | Antiherpético | — | `/farmacia/dermatologia/antiherpetico` | F1A12B2 |
| Dermatología | Antimicóticos | — | `/farmacia/dermatologia/antimicoticos` | F1A12B3 |
| Dermatología | Dermatología Especializada | — | `/farmacia/dermatologia/dermatologia-especializada` | F1A12B4 |
| Dermatología | Escabicidas | — | `/farmacia/dermatologia/escabicidas` | F1A12B5 |

### Paginación

- **URL:** `{ruta de categoría}?start={offset}&sz={tamaño}`. El HTML reporta el total como
  "N productos".
- **Tamaño de página:** el sitio usa 20; `sz=96` devolvió 96 y `sz=600` devolvió la categoría
  Analgésicos completa (597) en una sola respuesta de 4.3 MB y 13.8 s. Tope de `sz`: no observado.
- **Última página:** `start=576&sz=96` devolvió los 21 restantes (576 + 21 = 597).
- **"Más resultados"** usa `Search-UpdateGrid` bajo `/on/demandware.store/`, prohibido en robots.txt:
  no se usa.
- Sin tope de paginación observado (a diferencia de Walmart).

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí.** Cada tarjeta del listado
(`<div class="product" data-pid="…">`), renderizada en servidor, trae:

| Dato | Selector en la tarjeta |
| --- | --- |
| ID / SKU | atributo `data-pid` (= ID final de la URL de la ficha) |
| URL de la ficha | `.image-container a[href]` (relativa, termina en `-{id}.html`) |
| Imagen | `img.tile-image[src]` (`…/products/{id}_A_1280_AL.jpg`) |
| Nombre | `alt` / `title` de la imagen y el enlace del nombre |
| Precio normal (tachado) | `.price-before .value[content]` |
| Precio de oferta / actual | `.sales .value[content]` |
| Marca | presente en la tarjeta (selector exacto por definir en el spider) |

En Analgésicos, los 597 productos (`sz=600`) traen `.sales .value[content]`. Muestra recortada de 2
tarjetas en `muestras/listado_analgesicos_2_tarjetas.html`.

`data-pid` es el mismo identificador que el legado guarda como SKU (`span.sku` o el sufijo de la
URL), así que el histórico empata sin migración.

### Validación desde la oficina (sin navegador, curl_cffi)

| Petición | Sin impersonar | Impersonando Chrome |
| --- | --- | --- |
| Listado Analgésicos `?start=0&sz=96` | reset HTTP/2 (3/3) | **200** (3/3), p50 2.64 s, 1.15 MB, 96 productos con precio |
| Ficha Naxen 15 tabletas | reset HTTP/2 (3/3) | **200** (3/3), p50 1.01 s, 518 KB |
| Conteos `?sz=1` de 29 categorías | — | 200 en todas; un reset tras ~12 seguidas a 3 s, ninguno a 10 s |

## Ficha de producto

**No hace falta para la corrida (f = 0).** Lo que trae:

- **JSON-LD `Product`:** `sku` = `mpn` = ID (`1184105`), `name`, `brand.name` (`NAXEN`), `image[]`,
  `offers.price` (precio de oferta, `238.74`), `offers.priceCurrency` (`MXN`), `offers.availability`.
  Muestra en `muestras/ficha_naxen_1184105.json`.
- **HTML:** el mismo bloque de precios que la tarjeta (`.price-before .value[content]` = `346.00`,
  `.sales .value[content]` = `238.74`). Coinciden con lo visible en pantalla.
- **Sin EAN:** ni `gtin` en el JSON-LD ni código de barras en el HTML o en pantalla; solo
  "SKU: 1184105". El cruce con el catálogo NDF seguirá siendo por texto (sección de entity
  resolution de `transform/`).
- **Disponibilidad:** sin código postal, el JSON-LD marca `OutOfStock` aunque el botón "Agregar" está
  visible (2 de 3 fichas). **No es confiable sin ubicación:** el spider no debe usarla como señal de
  baja del producto.

### Sucursal o zona

- **No hay ubicación por defecto.** El encabezado pide "Elige una dirección de entrega" y la ficha
  "Ingresa un código postal para ver disponibilidad". No hay cookies de ubicación, tienda o código
  postal (ni legibles por script ni en los `Set-Cookie` observados).
- El sitio avisa: "Precios exclusivos online, sujeto a variaciones por ubicación y diferente a tienda
  física". Los términos dicen que los precios de la página pueden "variar en comparación de los
  precios en sucursal".
- **Sucursal de referencia:** ninguna; se captura el precio online sin ubicación (`zona_precio =
  sin_ubicacion`). Si se quisiera una zona, el selector usa `/FGAddZoneAttributes`, prohibido en
  robots.txt. Si el precio sin ubicación difiere del de una zona concreta: no observado.

## Propuesta

### Escalón elegido: b, HTTP impersonado, sobre listados (f = 0)

- **Por qué no a:** sin impersonar, Akamai corta todas las conexiones.
- **Por qué b basta:** impersonando Chrome, listados y fichas responden 200 sin cookies previas ni
  desafío; el bloqueo es solo por huella TLS y por ritmo.
- **f = 0:** el listado trae ID, URL, nombre, imagen, precio normal y precio de oferta. No se abren
  las fichas (el legado abre un Chrome por cada una: ~85 h).

### Estrategia de cobertura

1. `tiendas.yml` declara las categorías de nivel 2 en alcance (configurable): las 12 de Farmacia,
   las 7 de Dermo, las 9 de Super y Pharmalife.
2. Para cada una pide `?start=0&sz=96` y lee "N productos"; pagina con `start += 96` hasta cubrir N.
   (`sz` mayor reduce peticiones, pero cada respuesta pesa más; 96 es el valor medido con p50 2.6 s.)
3. Deduplica por `data-pid` y guarda las categorías de cada producto.
4. **Cobertura por corrida:** únicos capturados contra el inventario del sitemap (11,797 IDs) y contra
   "N productos" de cada categoría. Los IDs del sitemap que no aparezcan en ningún listado indican
   categorías faltantes en `tiendas.yml`.
5. **Ritmo:** 1 petición cada 10 s (C = 1). Con eso no se repitió el reset de Akamai; ante un reset,
   espera de 90 s o más antes de reintentar (circuit breaker de la Metodología).

### Presupuesto (sección 5)

Supuestos: ipp = 96, f = 0, Z = 1, C = 1, L = 2.6 s (medida), d = 10 s, r = 0.1. q = mín(C / L,
1 / d) = 0.1 req/s.

| Alcance en `tiendas.yml` | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Medicina (`/farmacia/medicina`) | 3,575 | 38 | ~0.1 h | ✅ |
| Raíz Farmacia (12 categorías) | 7,019 | ~78 | ~0.2 h | ✅ |
| Catálogo completo (29 categorías) | 11,797 únicos | ~169 (redondeo por categoría) | ~0.5 h | ✅ |

El catálogo completo cabe con holgura: **frente a las ~85 h del legado, menos de 1 h.**

### Riesgos

- **Akamai por ritmo:** reset tras ~12 peticiones a 3 s; el delay de 10 s lo evita (verificar en la
  primera corrida completa).
- **Términos de uso 3.2 y 3.3:** restringen el uso comercial; escalar a Aldo.
- **Zona de precio:** se captura sin ubicación; si el precio cambia por zona, la serie refleja el
  precio online base.
- **Sin EAN:** el cruce con el catálogo NDF depende del texto.
- **Disponibilidad sin ubicación no es confiable** (`OutOfStock` con botón "Agregar" visible).
- **Contrato del HTML:** los selectores de la tarjeta (`data-pid`, `.sales .value[content]`) son de
  SFRA estándar, pero un cambio de tema los rompe.
