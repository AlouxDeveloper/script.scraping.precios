# Reconocimiento: Farmacias GI

- **URL:** https://farmaciasgi.com.mx
- **Slug:** gi
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); pendiente Aldo con Claude in Chrome
  para CAPTCHA y precio en pantalla
- **Entorno:** oficina o nube (sin WAF)

Se reconoció por HTTP. Se confirma la hipótesis del issue: es WooCommerce y la Store API está
abierta, así que el Selenium del legado (URLs por categoría y luego ficha por ficha) se reemplaza
por 18 peticiones JSON.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** WordPress + WooCommerce, tema Astra con Elementor, servidor Apache.
- **Sin WAF:** la Store API responde 200 sin impersonar y sin User-Agent (5 de 5, p50 1.73 s) y con
  impersonación de Chrome (5 de 5, p50 1.90 s). No pide nonce, cookies ni token para leer.
- **Navegador:** el HTML no carga reCAPTCHA ni Cloudflare. Por verificar en el navegador.

### robots.txt

`User-agent: *` prohíbe `/wp-admin/` (salvo `admin-ajax.php`), tres carpetas de `uploads` de
WooCommerce y `/*?add-to-cart=`. **No prohíbe `/wp-json/`, catálogo ni producto.** Sin
`Crawl-delay`. Sitemaps en `/sitemap.xml` y `/sitemap.rss`.

### Términos de uso

**No hay términos publicados.** `/terminos-y-condiciones/` (modificada el 2024-05-22, leída por
`/wp-json/wp/v2/pages`) solo tiene una imagen con el título y un enlace al aviso de privacidad, que
trata de datos personales. No hay cláusulas de uso comercial, reproducción ni robots.

## Sucursal

**No aplica.** WooCommerce maneja un solo precio por producto: ni la API ni la ficha reciben
sucursal, CP ni sesión. La página `/sucursales/` es informativa. Precio único del sitio.

## Categorías y paginación

`/wp-json/wc/store/v1/products/categories` lista 48 categorías, casi todas en la raíz y mezcladas
con campañas (`10p`, `25p`, `25-aniversario`, `dia-del-padre`, `la-magia-del-amor`, `ofertas`).
Hay duplicados por carga (`fraccion-v` y `fraccion-v-2`, `mama-y-bebe` y `mama-y-bebe-2`).

Las de medicamentos (conteo de la API):

| Categoría | ID | Productos |
| --- | --- | --- |
| Medicamentos A – Z | 53 | 509 |
| Fracción IV | 212 | 207 |
| Fracción VI (hija de 53) | 58 | 145 |
| Antibióticos | 43 | 116 |
| Medicamentos de venta libre (OTC) | 88 | 54 |
| Fracción V (hija de 53) | 87 | 14 |
| Fracción IV (Medicamentos A-Z) | 292 | 12 |
| Trideboce (hija de 53) | 66 | 4 |
| Fracción VI (OTC), Fracción V (2) | 293, 298 | 3, 1 |

- **Únicos en esas categorías: 898** de 1,778.
- **216 productos no tienen categoría**, y 101 de ellos tienen forma farmacéutica en el nombre
  (`PORTEM AS 500/50 MG C/20 TAB`, `BRUFEM 400/20 MG C/10 TAB`…). Recorrer por categoría los
  perdería.
- **Propuesta:** recorrer el catálogo completo (1,778, 18 páginas) y filtrar después. Cuesta lo
  mismo que ir por categoría y no depende de un árbol desordenado.

### Paginación y tope

- `per_page` (máximo 100; con 101 responde 400) y `page` (base 1).
- `x-wp-total` = 1,778 y `x-wp-totalpages` = 18. La página 19 responde 200 con `[]`.
- Sin tope: 18 páginas trajeron los 1,778 `id` únicos. El HTML del catálogo dice lo mismo
  ("Mostrando 1–16 de 1778 resultados").

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0).**

`GET https://farmaciasgi.com.mx/wp-json/wc/store/v1/products?per_page=100&page=N`

| Dato | Ruta en el JSON |
| --- | --- |
| SKU (= SKU del legado, `span.sku`) | `[].sku` (código interno de 6 dígitos) |
| ID de WooCommerce | `[].id` |
| Nombre | `[].name` |
| URL de la ficha | `[].permalink` |
| Categorías | `[].categories[].slug` |
| Imagen | `[].images[0].src` |
| **Precio de lista** | `[].prices.regular_price` (en centavos: `currency_minor_unit = 2`) |
| **Precio de venta** | `[].prices.price` (= `sale_price` cuando hay oferta) |
| Oferta | `[].on_sale` |
| Existencia | `[].is_in_stock` |

Muestra con 2 productos en `muestras/store_api_products_2.json` (descripciones recortadas).

- **Precios en centavos:** `"11000"` = $110.00. Dividir entre `10 ** currency_minor_unit`.
- **Sin EAN:** el catálogo no lo publica.
- **Todos son `simple`:** no hay variaciones.
- **Casos raros:** 11 productos sin SKU (Bruluart y otros; usar `id` como respaldo) y 1 con precio
  0 (`510219` Flanax 275 mg). Ningún SKU repetido.
- **Ofertas:** hoy `on_sale = false` en los 1,778. El legado tenía 76 con oferta en septiembre
  (p. ej. Ceftriaxona 75 → 60); hoy esos mismos están a precio regular en la API y en el HTML, así
  que las ofertas terminaron. El spider toma `regular_price` y `price` y no depende de `on_sale`.

### Empate con el legado

- El legado guarda `SKU = span.sku`, `Precio_Actual = <del>` (o el precio único) y
  `Precio_Oferta = <ins>` (o el mismo precio): equivale a `regular_price` y `price`.
- Los 1,069 SKU válidos del CSV de septiembre están en la API. 669 empatan en precio; los demás
  cambiaron de precio en octubre (subidas y bajadas). En 4 revisados, la API coincide con el
  precio que muestra hoy la ficha HTML.
- **369 filas del legado son `N/A`**: URLs que hoy responden 404. El legado recorría una lista de
  URLs vieja (el Excel de categorías ya no está en el equipo).
- **Cobertura:** el legado traía 1,069 productos válidos; el spider trae 1,778 (898 en categorías
  de medicamentos, más los sin categoría).

## Ficha de producto

No hace falta (f = 0).

## Propuesta

### Escalón elegido: a, API JSON sin impersonar (f = 0)

La Store API es pública, sin WAF, y trae precio de lista, precio de venta, SKU y categorías.
Encaja en una base WooCommerce reutilizable: solo cambia el dominio.

### Estrategia de cobertura

1. `GET /wp-json/wc/store/v1/products?per_page=100&page=N` desde 1 hasta `x-wp-totalpages` o una
   respuesta `[]`.
2. Deduplicar por `id` (no por `sku`: hay 11 vacíos).
3. **Cobertura por corrida:** únicos contra `x-wp-total`.
4. El filtro de medicamentos se hace después, en la capa de datos, no en la captura.
5. **Ritmo:** 1 petición cada 2 s (C = 1). Cada página pesa unos 300 KB y tarda casi 2 s: es un
   WordPress compartido, no hay que apretarlo.

### Presupuesto (sección 5)

Supuestos: ipp = 100, f = 0, Z = 1, C = 1, L = 1.9 s (medida), d = 2 s, r = 0.05.

| Alcance | Productos | Páginas R | Horas H | Semáforo |
| --- | --- | --- | --- | --- |
| Catálogo completo | 1,778 | 18 | ~0.02 h | ✅ |

Poco más de un minuto, contra más de hora y media de Selenium del legado (1,438 fichas a unos 4 s
cada una, más las páginas de categoría).

### Riesgos

- **Taxonomía desordenada:** 216 productos sin categoría y campañas mezcladas con categorías. Por
  eso se recorre todo.
- **Store API:** WooCommerce la trae activa por defecto; si la desactivan, el respaldo es el HTML
  del catálogo (`a.ast-loop-product__link` y `p.price`, 16 por página, 112 páginas).
- **Precios en centavos:** un error de conversión multiplica por 100.
- **11 sin SKU y 1 con precio 0:** el spider no debe descartarlos en silencio.
- **Términos de uso:** no hay; solo aviso de privacidad.
