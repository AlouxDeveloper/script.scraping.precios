# Reconocimiento: Bodega Aurrera

- **URL:** https://www.bodegaaurrera.com.mx
- **Slug:** aurrera
- **Fecha:** 2026-10-07
- **Quién:** Aldo (con Claude in Chrome, extensión, desde Windows nativo); revisión de Claude Code
- **Entorno:** solo oficina

Comparte plataforma con Walmart México: este documento confirma lo igual y detalla solo lo que
cambia. Para todo lo que no se repite aquí (campos de la ficha, GraphQL persistido, headers `x-o-*`,
razonamiento del escalón) ver `../walmart/notas.md`.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`. Las capturas de los
desafíos quedan locales en `salida/reconocimiento/aurrera/` (fuera de git).

## Plataforma y protección

- **Plataforma:** Next.js sobre el stack de Walmart. `__NEXT_DATA__` en home, listados y ficha;
  `buildId = production_20261001T012440882Z-es-MX`. Scripts `/_next/static/` servidos desde
  `i5-mx.walmartimages.com` (145 en la home).
- **HUMAN/PerimeterX, confirmado:** cookies `_px3`, `_pxvid`, `__pxvid`, `_pxde`, `pxcts`; script
  propio `/px/PXAFlYiz9n/init.js`; **`_pxAppId = PXAFlYiz9n`, el mismo que Walmart.**
- **Akamai: no observado.** Ni en el navegador (cookies legibles por script) ni en los `Set-Cookie`
  de la respuesta sin navegador aparecen `_abck`, `bm_sz`, `bm_sv` o `ak_bmsc`. En Walmart sí.
- **Cookies `TS…`:** presentes, como en Walmart (prefijo habitual de F5 BIG-IP; hipótesis).
- Nombres de cookies visibles por script: `TS013fee67`, `TS01498ee1`, `TS01782124`, `TS01a49e66`,
  `TS9003c8fa027`, `__pxvid`, `_astc`, `_ga`, `_ga_JQF33GB6MT`, `_gcl_au`, `_intlbu`, `_px3`,
  `_pxde`, `_pxvid`, `_shcc`, `adblocked`, `assortmentStoreId`, `bstc`, `exp-ck`, `hasACID`,
  `hasLocData`, `mmuid`, `pxcts`, `seqnum`, `userAppVersion`, `vtc`, `xpa`, `xpm`, `xptwj`.
- `Set-Cookie` de la respuesta sin navegador (solo nombres): `ACID`, `AID`, `TS…` (6),
  `_intlbu`, `_m`, `_shcc`, `assortmentStoreId`, `bstc`, `com.wm.reflector`, `exp-ck`, `hasACID`,
  `hasLocData`, `locDataV3`, `locGuestData`, `mocksConfig.v2`, `seqnum`, `userAppVersion`, `vtc`,
  `xpa`, `xpm`, `xptc`, `xpth`, `xptwj`.

### robots.txt

```text
User-agent: *

Disallow: /cart*
Disallow: /tu-cuenta*
Disallow: /checkout*
Disallow: /search*
Disallow: /wallet*
Disallow: /account*
Disallow: /thankyou*
Disallow: https://www-qa.bodegaaurrera.com.mx/*

# Sitemap XML
Sitemap: https://www.bodegaaurrera.com.mx/siteindex.xml
```

- **Riesgo informado:** `/search*` en Disallow, **sin** la excepción `Allow: /search?*z=1` que tiene
  Walmart. La búsqueda queda descartada.
- `/browse/` e `/ip/` permitidos; sin `Crawl-delay`.
- Sitemap `siteindex.xml` (1,932 sitemaps hijos medidos el 2026-10-01).
- **ToS:** por verificar.

### Desafíos

Dos desafíos de HUMAN ("Verifica tu identidad / Mantén presionado"), resueltos por una persona por
decisión de Aldo (la Metodología dice detenerse):

| # | Página | Momento |
| --- | --- | --- |
| 1 | `/` (home) | Tercera carga de la sesión, justo después de `robots.txt` |
| 2 | `/blocked`, probablemente al entrar a Equipo Médico | Tras 9 cargas seguidas con ~3 s de separación |

En las últimas 10 cargas, espaciadas a 10 s, no apareció ninguno. Es consistente con Walmart (un
desafío cada 8 a 10 páginas) y sugiere que el ritmo también cuenta, no solo el volumen.

## Categorías y paginación

- **Entrada desde el menú:** Departamentos → "Farmacia y Cuidado de la Salud" → "Ver Todos" →
  `/content/farmacia-y-cuidado-de-la-salud/264536`. Esa página `/content/` usa
  `pageProps.initialTempoData`, no trae facetas ni `cat_id`.
- **Listado de nivel 1:** `/browse/farmacia-y-cuidado-de-la-salud/264536` (URL armada con el patrón;
  no viene del menú), `aggregatedCount = 266,270`.
- **Mismo ID de rama que Walmart (`264536`) y mismos IDs de ramas y hojas.**
- **Faceta `cat_id`:** en nivel 1 está en `searchResult.modules.allSortAndFilterFacets` y en
  `contentLayout.modules[6].configs`; en Medicamentos `searchResult.modules` viene vacío y solo está
  en `contentLayout.modules[6].configs` (módulo `SearchSortFilterModule`). El spider debe buscar el
  módulo por tipo, no por índice. Los valores de la faceta traen `itemCount`, no `aggregatedCount`,
  y no hay nodo de nivel 1. Cada listado trae solo un nivel de hijos.
- **Diferencia de URL con Walmart:** la URL de la hoja **no** lleva el slug de la rama:
  `/browse/farmacia-y-cuidado-de-la-salud/{slug-hoja}/{ID completo}`. Los slugs de `baseSeoURL`
  reemplazan cada acento por `-` (`analg-sicos`, `antimic-ticos`). Con slugs escritos a mano sin
  acentos, la página también cargó (el ID es lo que manda).

### Ramas de nivel 2

`itemCount` es el de la faceta del nivel 1; `aggregatedCount` el del listado propio. No coinciden.
`*` = slug escrito sin acentos por Claude in Chrome (cargó bien; el canónico no se observó).

| Rama | ID | itemCount | Slug | Hojas | aggregatedCount |
| --- | --- | --- | --- | --- | --- |
| Equipo Ortopédico | `264536_264578` | 127,240 | `equipo-ortopedico` | 15 | 119,661 |
| Equipo Médico | `264536_264564` | 85,621 | `equipo-medico` | 14 | 83,953 |
| Accesorios para Farmacia y Cuidado de la salud | `264536_2067466` | 20,927 | `accesorios-para-farmacia-y-cuidado-de-la-salud` | 17 | 27,969 |
| Fajas y Control de Peso | `264536_264552` | 15,810 | `fajas-y-control-de-peso` | 5 | 15,465 |
| Oftálmicos y Óticos | `264536_264594` | 10,073 | `oftalmicos-y-oticos` * | 8 | 6,990 |
| Material de Curación | `264536_970119` | 7,248 | `material-de-curacion` * | 12 | 6,857 |
| Vitaminas y Suplementos | `264536_264549` | 5,676 | `vitaminas-y-suplementos` | 8 | 5,679 |
| Incontinencia | `264536_264537` | 5,567 | `incontinencia` | 4 | 5,569 |
| Botiquines | `264536_265802` | 5,307 | `botiquines` | 5 | 5,444 |
| Diabetes | `264536_960017` | 4,274 | `diabetes` | 4 | 3,920 |
| Destacados Farmacia y Cuidado de la Salud | `264536_300056` | 2,513 | `destacados-farmacia-y-cuidado-de-la-salud` | 2 | 2,513 |
| Nutrición Deportiva | `264536_1520006` | 2,253 | `nutricion-deportiva` * | 1 | 2,066 |
| Medicamentos | `264536_1310112` | 1,939 | `medicamentos` | 25 | 1,959 |
| Bienestar Sexual | `264536_264585` | 758 | `bienestar-sexual` | 6 | 741 |
| Higiene Íntima e Incontinencia | `264536_264543` | 318 | `higiene-intima-e-incontinencia` * | 2 | 275 |
| Sueros y Orales | `264536_1520002` | 147 | `sueros-y-orales` | 3 | 149 |

### Hojas

ID completo = `{ID de la rama}_{sufijo}`. Mismos sufijos que Walmart; cambian los conteos. Slugs de
`baseSeoURL`.

**Medicamentos** (`264536_1310112_`):

| Hoja | Sufijo | itemCount | Slug |
| --- | --- | --- | --- |
| Alta Especialidad | 120504 | 1,114 | `alta-especialidad` |
| Otros Medicamentos | 2470029 | 1,134 | `otros-medicamentos` |
| Antimicóticos | 2470026 | 261 | `antimic-ticos` |
| Medimart | 120505 | 223 | `medimart` |
| Antigripales | 2460013 | 142 | `antigripales` |
| Congestión Nasal | 120514 | 116 | `congesti-n-nasal` |
| Antiinflamatorios | 2470001 | 74 | `antiinflamatorios` |
| Analgésicos | 2410125 | 70 | `analg-sicos` |
| Oftálmicos | 2470028 | 67 | `oft-lmicos` |
| Antiulcerantes | 120482 | 59 | `antiulcerantes` |
| Dolor | 120493 | 57 | `dolor` |
| U-V-W-X-Y | 120470 | 57 | `u-v-w-x-y` |
| Digestivos | 2410120 | 53 | `digestivos` |
| Anti-tabaco | 3200034 | 47 | `anti-tabaco` |
| Antiácidos | 120484 | 28 | `anti-cidos` |
| Tos | 120513 | 28 | `tos` |
| Antidiarreicos | 120483 | 24 | `antidiarreicos` |
| Laxante | 120481 | 24 | `laxante` |
| Antiparasitarios | 120480 | 14 | `antiparasitarios` |
| Antihistamínicos | 2470024 | 12 | `antihistam-nicos` |
| Dolor y Malestar | 3200039 | 10 | `dolor-y-malestar` |
| Presión Arterial | 2470030 | 8 | `presi-n-arterial` |
| Dolor de Garganta | 2470027 | 6 | `dolor-de-garganta` |
| Hemorroides | 120495 | 4 | `hemorroides` |
| Pastillas | 120497 | 4 | `pastillas` |

**Resto de ramas:**

| Rama | Hoja | Sufijo | itemCount | Slug |
| --- | --- | --- | --- | --- |
| Accesorios para Farmacia | Accesorios de Nutrición Deportiva | 1520013 | 2,196 | `accesorios-de-nutrici-n-deportiva` |
| Accesorios para Farmacia | Accesorios para Bienestar Sexual | 960028 | 273 | `accesorios-para-bienestar-sexual` |
| Accesorios para Farmacia | Aceites y Cremas | 3200021 | 1,246 | `aceites-y-cremas` |
| Accesorios para Farmacia | Antimicóticos Pies | 3200062 | 47 | `antimic-ticos-pies` |
| Accesorios para Farmacia | Antimicóticos Uñas | 3200063 | 22 | `antimic-ticos-u-as` |
| Accesorios para Farmacia | Antipiojos | 3200019 | 5 | `antipiojos` |
| Accesorios para Farmacia | Bucales | 3200015 | 1,169 | `bucales` |
| Accesorios para Farmacia | Cremas | 3200027 | 2,599 | `cremas` |
| Accesorios para Farmacia | Cuidado de la Piel | 3200017 | 1,238 | `cuidado-de-la-piel` |
| Accesorios para Farmacia | Cuidado de los Labios | 120488 | 44 | `cuidado-de-los-labios` |
| Accesorios para Farmacia | Cuidado Personal | 3200069 | 9,858 | `cuidado-personal` |
| Accesorios para Farmacia | Desodorantes | 3200068 | 1,976 | `desodorantes` |
| Accesorios para Farmacia | Estomacales | 3200079 | 65 | `estomacales` |
| Accesorios para Farmacia | Polvos | 3200026 | 250 | `polvos` |
| Accesorios para Farmacia | Quemaduras y Protectores | 120487 | 97 | `quemaduras-y-protectores` |
| Accesorios para Farmacia | Repelentes | 120486 | 1,766 | `repelentes` |
| Accesorios para Farmacia | Talcos | 3200067 | 56 | `talcos` |
| Bienestar Sexual | Accesorios | 3200050 | 1 | `accesorios` |
| Bienestar Sexual | Accesorios para Bienestar Sexual | 960028 | 308 | `accesorios-para-bienestar-sexual` |
| Bienestar Sexual | Condones y Anticonceptivos | 264591 | 118 | `condones-y-anticonceptivos` |
| Bienestar Sexual | Juguetes Sexuales | 0293155 | 36 | `juguetes-sexuales` |
| Bienestar Sexual | Lubricantes y Humectantes | 264589 | 320 | `lubricantes-y-humectantes` |
| Bienestar Sexual | Pruebas de Embarazo y Ovulación | 960027 | 34 | `pruebas-de-embarazo-y-ovulaci-n` |
| Botiquines | Cubre Bocas y Caretas | 265962 | 3,635 | `cubre-bocas-y-caretas` |
| Botiquines | Gasas y Vendas | 265963 | 658 | `gasas-y-vendas` |
| Botiquines | Gel Antibacterial | 265964 | 340 | `gel-antibacterial` |
| Botiquines | Guantes y Cubrebocas | 3200041 | 5 | `guantes-y-cubrebocas` |
| Botiquines | Jeringas | 265801 | 676 | `jeringas` |
| Destacados | Farmacia y Cuidado de la Salud - Envío Internacional | 760065 | 1,992 | `farmacia-y-cuidado-de-la-salud-env-o-internacional` |
| Destacados | Lo Más Vendido - Farmacia y Cuidado de la Salud | 300057 | 2,439 | `lo-m-s-vendido-farmacia-y-cuidado-de-la-salud` |
| Diabetes | Glucómetros | 960018 | 63 | `gluc-metros` |
| Diabetes | Jeringas | 960021 | 728 | `jeringas` |
| Diabetes | Medias y Calcetines | 960022 | 3,104 | `medias-y-calcetines` |
| Diabetes | Tiras Reactivas y Lancetas | 960019 | 384 | `tiras-reactivas-y-lancetas` |
| Equipo Médico | Baumanómetros, Oxímetros y Pulsómetros | 264567 | 114 | `bauman-metros-ox-metros-y-puls-metros` |
| Equipo Médico | Camas de Hospital y Colchones | 264569 | 108 | `camas-de-hospital-y-colchones` |
| Equipo Médico | Cámaras de Bronceado y UV | 264577 | 20 | `c-maras-de-bronceado-y-uv` |
| Equipo Médico | Equipo para tu Salud | 960016 | 10,513 | `equipo-para-tu-salud` |
| Equipo Médico | Equipos de Laboratorio | 264576 | 24,079 | `equipos-de-laboratorio` |
| Equipo Médico | Equipos y Accesorios | 3200072 | 114 | `equipos-y-accesorios` |
| Equipo Médico | Humidificadores y Vaporizadores | 264566 | 17,836 | `humidificadores-y-vaporizadores` |
| Equipo Médico | Instrumental Médico | 264575 | 19,309 | `instrumental-m-dico` |
| Equipo Médico | Monitores de Presión | 960015 | 87 | `monitores-de-presi-n` |
| Equipo Médico | Nebulizadores | 264570 | 136 | `nebulizadores` |
| Equipo Médico | Ortopedia y Equipos de Medición | 3200081 | 13,047 | `ortopedia-y-equipos-de-medici-n` |
| Equipo Médico | Oxígeno y Productos para Oxígenoterapia | 264568 | 1,006 | `ox-geno-y-productos-para-ox-genoterapia` |
| Equipo Médico | Respiratorios | 3200082 | 14,649 | `respiratorios` |
| Equipo Médico | Termómetros | 264565 | 363 | `term-metros` |
| Equipo Ortopédico | Accesorios | 3200065 | 34,007 | `accesorios` |
| Equipo Ortopédico | Accesorios (otro ID) | 3200061 | 33,999 | `accesorios` |
| Equipo Ortopédico | Andaderas | 264579 | 2,017 | `andaderas` |
| Equipo Ortopédico | Bastones | 960012 | 4,178 | `bastones` |
| Equipo Ortopédico | Callos, Ampollas y Juanetes | 3200066 | 5,807 | `callos-ampollas-y-juanetes` |
| Equipo Ortopédico | Collarines y Férulas | 264584 | 11,539 | `collarines-y-f-rulas` |
| Equipo Ortopédico | Cuidado de los Pies | 3200077 | 6,421 | `cuidado-de-los-pies` |
| Equipo Ortopédico | Cuidado del Paciente y Aseo | 264582 | 29,687 | `cuidado-del-paciente-y-aseo` |
| Equipo Ortopédico | Cuidado Personal | 3200078 | 5,466 | `cuidado-personal` |
| Equipo Ortopédico | Fajas Ortopédicas | 264554 | 5,506 | `fajas-ortop-dicas` |
| Equipo Ortopédico | Masajeadores | 960014 | 16,490 | `masajeadores` |
| Equipo Ortopédico | Muletas | 960013 | 1,209 | `muletas` |
| Equipo Ortopédico | Ortopedia y Rehabilitación | 264580 | 54,204 | `ortopedia-y-rehabilitaci-n` |
| Equipo Ortopédico | Plantillas | 3200064 | 11,919 | `plantillas` |
| Equipo Ortopédico | Sillas de Ruedas | 264581 | 3,503 | `sillas-de-ruedas` |
| Fajas y Control de Peso | Básculas y Medidores de Grasa | 264553 | 1,975 | `b-sculas-y-medidores-de-grasa` |
| Fajas y Control de Peso | Fajas Ortopédicas | 264554 | 5,613 | `fajas-ortop-dicas` |
| Fajas y Control de Peso | Medias de Compresión | 264557 | 3,104 | `medias-de-compresi-n` |
| Fajas y Control de Peso | Productos Terapéuticos | 264555 | 3,112 | `productos-terap-uticos` |
| Fajas y Control de Peso | Suplementos Dietéticos | 264551 | 2,024 | `suplementos-diet-ticos` |
| Higiene Íntima e Incontinencia | Predoblados | 3200036 | 2 | `predoblados` |
| Higiene Íntima e Incontinencia | Toallas y Copas Menstruales | 264544 | 273 | `toallas-y-copas-menstruales` |
| Incontinencia | Calzones Anatómicos | 264538 | 23 | `calzones-anat-micos` |
| Incontinencia | Pañales para Adultos | 264548 | 2,239 | `pa-ales-para-adultos` |
| Incontinencia | Ropa Interior | 264539 | 3,482 | `ropa-interior` |
| Incontinencia | Toallas Protectoras | 960035 | 2,090 | `toallas-protectoras` |
| Material de Curación | Alcohol | 860019 | 31 | `alcohol` |
| Material de Curación | Algodón | 860020 | 1,020 | `algod-n` |
| Material de Curación | Banditas | 265961 | 4,515 | `banditas` |
| Material de Curación | Cintas Kinesiológicas | 3200045 | 322 | `cintas-kinesiol-gicas` |
| Material de Curación | Cubre Bocas y Caretas | 265962 | 2 | `cubre-bocas-y-caretas` |
| Material de Curación | Gasas y Vendas | 265963 | 1 | `gasas-y-vendas` |
| Material de Curación | Hisopos | 860021 | 1,037 | `hisopos` |
| Material de Curación | Jeringas | 265801 | 8 | `jeringas` |
| Material de Curación | Material de Curación | 3200080 | 130 | `material-de-curaci-n` |
| Material de Curación | Otros | 3200046 | 10 | `otros` |
| Material de Curación | Pomadas Antisépticas | 860025 | 18 | `pomadas-antis-pticas` |
| Material de Curación | Soluciones Antisépticas | 3200044 | 35 | `soluciones-antis-pticas` |
| Nutrición Deportiva | Accesorios de Nutrición Deportiva | 1520013 | 2,254 | `accesorios-de-nutrici-n-deportiva` |
| Oftálmicos y Óticos | Gotas para ojos | 3200051 | 62 | `gotas-para-ojos` |
| Oftálmicos y Óticos | Lentes | 120510 | 3,266 | `lentes` |
| Oftálmicos y Óticos | Lentes de Contacto | 264597 | 2,174 | `lentes-de-contacto` |
| Oftálmicos y Óticos | Lentes Oftálmicos Hombre | 264661 | 5,279 | `lentes-oft-lmicos-hombre` |
| Oftálmicos y Óticos | Lentes Oftálmicos Mujer | 264660 | 6,364 | `lentes-oft-lmicos-mujer` |
| Oftálmicos y Óticos | Lentes para niños | 264659 | 135 | `lentes-para-ni-os` |
| Oftálmicos y Óticos | Oído | 1520009 | 133 | `o-do` |
| Oftálmicos y Óticos | Soluciones para Lentes de Contacto | 1520007 | 259 | `soluciones-para-lentes-de-contacto` |
| Sueros y Orales | Sueros | 120479 | 130 | `sueros` |
| Sueros y Orales | Sueros Efervescentes | 1520005 | 38 | `sueros-efervescentes` |
| Sueros y Orales | Sueros Líquidos | 1520001 | 70 | `sueros-l-quidos` |
| Vitaminas y Suplementos | Clorofilas | 120509 | 21 | `clorofilas` |
| Vitaminas y Suplementos | Herbolarias y Naturistas | 960025 | 593 | `herbolarias-y-naturistas` |
| Vitaminas y Suplementos | Multivitamínicos | 960024 | 481 | `multivitam-nicos` |
| Vitaminas y Suplementos | Otros Medicina y Suplementos | 264631 | 5 | `otros-medicina-y-suplementos` |
| Vitaminas y Suplementos | Proteínas y Suplementos | 264550 | 4,991 | `prote-nas-y-suplementos` |
| Vitaminas y Suplementos | Suplementos Dietéticos | 264551 | 2,024 | `suplementos-diet-ticos` |
| Vitaminas y Suplementos | Vitaminas | 350098 | 547 | `vitaminas` |
| Vitaminas y Suplementos | Vitaminas y Suplementos | 3200083 | 693 | `vitaminas-y-suplementos` |

Como en Walmart, varias hojas se repiten bajo ramas distintas con el mismo sufijo (264554, 264551,
265962, 960028, 1520013) y la suma de hojas a veces supera el total de la rama: el spider deduplica
por `usItemId`.

### Paginación y tope

- 40 productos + 1 `AdPlaceholder` por página; `pageProperties.ps = "44"`.
- `maxPage` real en listados chicos (Antigripales 4, Sueros y Orales 4, Higiene Íntima 7, Bienestar
  Sexual 17) y **tope de 23** en el nivel 1 y en toda rama de más de ~1,000 productos, incluida
  Medicamentos (1,959). **Igual que Walmart.**
- Hojas de Medicamentos sobre el tope: Alta Especialidad (1,114) y Otros Medicamentos (1,134).

## Endpoints

- **Listado:** mismas rutas que Walmart en `props.pageProps.initialData.searchResult.itemStacks[0].items`
  (`price`, `priceInfo.linePrice`, `priceInfo.wasPrice`, `usItemId`, `name`, `canonicalUrl`,
  `imageInfo.thumbnailUrl`, `availabilityStatusV2`, `sellerName`, `sellerType`). Muestra en
  `muestras/listado_antigripales_p1.json`.
- En Antigripales, 7 de 40 traen `wasPrice`; vendedores "Bodega Aurrera" (`INTERNAL`) y "Farmacia
  Prixz" (`EXTERNAL`): marketplace mezclado, igual que Walmart.
- **`?page=2` con recarga completa (navegador):** 40 productos con `price` en `__NEXT_DATA__`,
  distintos de los de la página 1. Cada página es autosuficiente por URL.

### Validación desde la oficina (sin navegador, curl_cffi)

| Petición | Sin impersonar | Impersonando Chrome |
| --- | --- | --- |
| Antigripales, página 1 | 307 → `/blocked` | **429** la primera vez; luego **200** (~490 KB, `x-prerender-apache-hit: true`, 40 productos con precio, `stores: 2769`) |
| Antigripales, `?page=2` | 307 → `/blocked` | **307 → `/blocked`** |

**Mismo patrón que Walmart:** solo la página 1 de cada listado pasa sin navegador (prerender); la
página N se bloquea. El 429 es nuevo: Aurrera aplica además un límite de tasa a peticiones seguidas
(la segunda llegó 5 s después). La ficha y el GraphQL no se validaron: se asume el mismo resultado
que en Walmart (307 / 412).

## Ficha de producto

Ficha: `/ip/Broncolin-Etiqueta-verde-250-ml-jarabe/00071470691059`. `product` en
`props.pageProps.initialData.data.product`; `product.id = 5PKG2UK80FD5`.

| Campo | Valor |
| --- | --- |
| `product.usItemId` | `00071470691059` |
| `product.upc` | `00071470691059` |
| JSON-LD `gtin13` | `00071470691059` |
| JSON-LD `sku` | `00071470691059` |

Precio 132 en `priceInfo.currentPrice.price` y en JSON-LD. **`usItemId` = EAN también en Aurrera.**
Como en Walmart, la ficha no hace falta para la corrida de precios (f = 0).

### Sucursal

- **Navegador:** "BA Hermanos Serdán, Blvd. Hermanos Serdán 797 Loc. A, Puebla, PUE 72116";
  `assortmentStoreId = 2769`, `hasLocData = 1`, `pageProperties.stores = "2769"`.
- **Sin navegador y sin cookies:** el servidor fija `assortmentStoreId` por `Set-Cookie` y el
  listado sale con `stores: 2769`, la misma sucursal. **Hipótesis:** el sitio asigna la sucursal por
  geolocalización de la IP (la de la oficina), no por una visita previa del navegador. En Walmart,
  sin cookie salió 3864 y en el navegador 2344, así que allá la asignación no fue la misma.
- Para una sucursal fija, el spider manda `assortmentStoreId` explícita, igual que en Walmart.

## Igual a Walmart / Distinto

| Aspecto | Aurrera | ¿Igual a Walmart? |
| --- | --- | --- |
| Plataforma Next.js + `__NEXT_DATA__` | Sí | Igual |
| HUMAN, `appId PXAFlYiz9n` | Sí | Igual |
| Akamai (`_abck`, `bm_sz`) | No observado | **Distinto** (Walmart sí) |
| Límite de tasa 429 sin navegador | Sí, una vez | **Distinto** (no visto en Walmart) |
| Rutas del listado y f = 0 | Sí | Igual |
| 40 por página, tope de 23 páginas | Sí | Igual |
| Página 1 por prerender sin navegador; página N bloqueada | Sí | Igual |
| `usItemId` = `upc` = `gtin13` | Sí | Igual |
| IDs de ramas y hojas | Mismos | Igual |
| URL de la hoja | Sin slug de rama | **Distinto** (Walmart lleva rama y hoja) |
| Faceta `cat_id` | Mismas rutas; módulo `contentLayout.modules[6]` | Igual (buscar por tipo) |
| robots.txt | Sin `Allow: /search?*z=1` | **Distinto** (sin efecto: no se usa búsqueda) |
| Sucursal | Cookie `assortmentStoreId`; 2769 Puebla también sin cookie | Mecanismo igual, valor distinto |
| Rama Medicamentos | 1,959 productos | Menos que Walmart (3,053) |
| Nivel 1 Farmacia | 266,270 | Más que Walmart (~237,000) |

## Propuesta

**Mismo escalón y estrategia que Walmart: d, navegador completo solo sobre listados (f = 0).**
El spider de Walmart se reutiliza cambiando la configuración: dominio, plantilla de URL de la hoja
(sin slug de rama) y sucursal. El razonamiento completo está en `../walmart/notas.md`.

Diferencias que la configuración debe cubrir:

- Plantilla de URL de hoja: `/browse/farmacia-y-cuidado-de-la-salud/{slug-hoja}/{ID}`.
- Sin Akamai: una capa de protección menos, pero el mismo HUMAN.
- Límite de tasa (429): respetar `DOWNLOAD_DELAY` y el backoff del middleware; con el escalón d y
  d = 5 s no debería aparecer.

### Presupuesto (sección 5), por alcance

Mismos supuestos que Walmart: ipp = 40, f = 0, Z = 1, C = 1, d = 5 s, r = 0.2, L = 15 s
(**hipótesis**, se mide en ALD-120), q = 1/15 req/s.

| Alcance en `tiendas.yml` | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Solo Medicamentos (25 hojas; 2 segmentadas) | 1,959 | ~104 | ~0.5 h | ✅ |
| Volumen del legado | 31,125 | ~779 | ~3.9 h | ✅ |
| Las 16 ramas | ~266,000 | ≥ 6,657 más la segmentación | ≥ 33 h | ⚠️, al borde del límite de 36 h |

El alcance de la v1 está pendiente de decisión de Aldo (igual que en Walmart).

### Riesgos

- **HUMAN:** desafío cada ~9 cargas seguidas a ~3 s; ninguno en 10 cargas a 10 s. Se valida en
  ALD-120 junto con Walmart.
- **Límite de tasa 429** sin navegador; por verificar con navegador.
- **Tope de paginación:** obliga a segmentar las hojas grandes.
- **Sucursal:** el valor por defecto depende de la IP; el spider debe fijarla.
- **ToS:** por verificar.
- El legado escribe el centinela `SEARCH` como SKU cuando cae en la página de búsqueda; el spider
  nuevo lee `usItemId` del JSON y no hereda ese error.
