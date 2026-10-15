# Reconocimiento: Farmacias ISSEG

- **URL:** https://farmaciasisseg.com.mx
- **Slug:** isseg
- **Fecha:** 2026-10-15
- **Quién:** Claude Code desde la oficina (HTTP con curl_cffi); pendiente Aldo con Claude in Chrome
  para el CAPTCHA en el navegador y precio en pantalla
- **Entorno:** solo oficina (WAF con huella TLS)

Se reconoció por HTTP leyendo el bundle de Angular del sitio: de ahí salen el host de la API, las
rutas y los términos de uso. El legado ya usaba esta API, pero sus URLs vivían en un Excel
(`salida/urls/url_catego_isseg.xlsx`) que ya no está en el equipo; aquí quedan documentadas.

Farmacias ISSEG es la cadena del Instituto de Seguridad Social del Estado de Guanajuato.

Evidencia en este directorio: `peticiones.txt`, `muestras/` y `validacion.csv`.

## Plataforma y protección

- **Plataforma:** SPA en Angular sobre una API ASP.NET Web API:
  `https://sapipedidossissegp.farmaciasisseg.com.mx/sapipedidossisseg/api/` (`BASE_API_URL` del
  entorno de producción). Sin `Accept: application/json` responde XML.
- **WAF: SafeLine (Chaitin)**, detrás de Tengine. Pone la cookie `sl-session` en todas las
  respuestas. Cuando bloquea responde **HTTP 468** con una página de CAPTCHA deslizable
  (`muestras/waf_468_safeline.html`).
- **Qué dispara el 468** (2026-10-15, `categorias`):

  | Impersonación | Referer | Resultado |
  | --- | --- | --- |
  | no | no | 468 |
  | no | sí | 468 |
  | Chrome | no | 468 |
  | Chrome | solo `Origin` | 468 |
  | Chrome | `Referer: https://farmaciasisseg.com.mx/` | **200** |

  Hacen falta las dos cosas: huella TLS de Chrome y `Referer` del sitio. No hacen falta cookies ni
  un primer GET al portal (el legado lo hace, pero sobra).
- **Ritmo tolerado:** 55 peticiones seguidas a `categorias/15` con pausas de 2, 1, 0.5 y 0 s, todas
  200. Más de 50 búsquedas pesadas con 1 a 3 s de pausa, todas 200 o 404 sin resultados. El WAF no limitó
  por ritmo en estas pruebas; el bloqueo es por huella y headers.

### Firma de bloqueo (`firmas_bloqueo`)

- `status == 468`.
- Cuerpo HTML de unos 14 KB con `<title>Validación de seguridad ISSEG</title>` y
  `SafeLineChallenge(` (host `waf.chaitin.com`).
- **No confundir con 404:** la búsqueda sin resultados responde 404 con cuerpo vacío.

### robots.txt

No hay. `farmaciasisseg.com.mx/robots.txt` devuelve el `index.html` de la SPA y el host de la API
responde 404 (página de IIS).

### Términos de uso

`https://farmaciasisseg.com.mx/terminos-y-condiciones` ("Términos y condiciones Farmacias ISSEG
2018"), leídos del bundle. Son **el mismo texto que los de San Pablo**:

- El sitio es "un medio de consulta … para consumo personal". "Cualquier otro uso incluyendo la
  reproducción … se encuentra estrictamente prohibido".
- "Queda terminantemente prohibido copiar … **descargar, almacenar**, reproducir … para
  comunicaciones no autorizadas o uso comercial sin el consentimiento previo por escrito".
- Cada usuario acepta no "explotar para fines comerciales ninguna parte de este sitio … ni recopilar
  información de visitantes".

**Riesgo a escalar a Aldo**, como San Pablo. Además el WAF declara de forma explícita que el sitio
"está protegido contra bots y tráfico automatizado".

## Sucursal

**No aplica.** Ni la categoría ni la búsqueda reciben sucursal ni CP (la búsqueda solo recibe
`idcliente`, 0 sin sesión). `existencia` viene en 0 y `disponibilidad` en `ALTA` en todos los
observados. Precio único del sitio.

## Categorías y paginación

`GET categorias`: 15 departamentos de un solo nivel (`idMenuPadre = null`), sin conteo. Medicamentos
es el **1**. La respuesta pesa 716 KB porque cada categoría trae su imagen en base64.

| ID | Departamento | Productos en `categorias/{id}` |
| --- | --- | --- |
| 1 | Medicamentos | 50 |
| 4 | Vitaminas y suplementos | 50 |
| 9 | Oftalmológicos y óticos | 50 |
| 12 | Salud sexual | 50 |
| 2, 3, 5, 6, 7, 8, 11 | Bebidas, Hogar, Cuidado personal, Equipo hospitalario, Derma, Bebés, Todo para la mujer | 50 cada uno |
| 13 | Dulces | 26 |
| 10 | Pañales adulto | 24 |
| 14 | Acc. ortopédicos | 9 |
| 15 | Mascotas | 3 |
| | **Únicos** | **612** |

### Tope de 50 por categoría

**`categorias/{id}` devuelve como máximo 50 productos y no pagina:** `pagina`, `page`, `skip`,
`offset`, `top` y `numeroPagina/tamanoPagina` devuelven los mismos 50. El sitio tampoco pide más:
la página de categoría llama solo a ese endpoint y pagina en el navegador.

**Esto explica el legado:** sus 613 filas son, casi exactas, los 50 primeros de cada departamento
(601 de 612 coinciden). El legado nunca vio el resto del catálogo.

### Búsqueda

`POST productos/busqueda` con `{"descripcion": "<texto>", "idcliente": 0}`:

- Busca por nombre y por principio activo (`paracetamol` trae 84, incluido Dalexidol, que es
  paracetamol con celecoxib). No busca por código de barras.
- **Tope de 100** resultados (`a`, `tab` y `metformina` llegan justo a 100).
- Sin resultados: **404 con cuerpo vacío**.
- **Pesada:** cada producto trae su imagen en base64, unos 128 KB. 40 búsquedas bajaron 142 MB.

### Tamaño del catálogo (estimado)

40 búsquedas por moléculas del catálogo NDF (las 30 más frecuentes y 10 al azar) trajeron **1,110
productos únicos**, de los que solo 52 están entre los 612 de categorías. La estimación por
captura-recaptura da **unos 13,000** productos; es gruesa porque las dos muestras no son
independientes, pero el campo `orden` llega a 8,088 y apunta al mismo orden de magnitud. **El
catálogo real es entre 10 y 20 veces lo que capturaba el legado.**

## Endpoints

**¿El listado trae el precio sin abrir la ficha? Sí (f = 0)**, en los dos endpoints.

| Dato | `categorias/{id}` | `productos/busqueda` |
| --- | --- | --- |
| SKU (= SKU del legado, EAN) | `codigoBarras` | `codigoBarras` |
| Nombre | `descripcionCorta` | `descripcion` |
| Principio activo | — | `componenteActivo` |
| Categoría | `idCategoria` | — |
| **Precio de lista** | `precioOriginal` | `precioVenta` |
| **Precio de venta** | `precioPublico` | `precioFinal` (= `precioVenta − descuento`) |
| Imagen | `imagen` (base64) y `nombre` (archivo, p. ej. `008400000248.jpg`) | `imagen` (base64) |
| Otros | `orden` | `antibiotico`, `disponibilidad`, `existencia`, `estatusDescuento` |

Muestras recortadas en `muestras/categorias_1_2.json` y `muestras/busqueda_losartan_2.json`.

- **Los dos endpoints dan el mismo precio:** en 5 productos revisados (3 con descuento),
  `precioOriginal = precioVenta` y `precioPublico = precioFinal`.
- **Empate con el legado:** el legado guarda `PRECIO_ACTUAL = precioOriginal` y
  `PRECIO_OFERTA = precioPublico`. De los 601 que están hoy en categorías, 492 empatan; el resto
  cambió de precio desde septiembre.
- **Imagen:** la API no publica URL de imagen, solo el base64. El legado guarda
  `data:image/png;base64,<nombre>`, que **no es una imagen válida** (pone el nombre de archivo
  donde va el base64). Propuesta: guardar solo la URL de la ficha
  (`https://farmaciasisseg.com.mx/producto/{codigoBarras}`) y dejar la imagen vacía, o el nombre de
  archivo como dato. El spider no debe guardar el base64.
- **SKU:** `codigoBarras`, de 12 a 14 dígitos en su mayoría; hay 3 de 8 y 1 de 4.

## Ficha de producto

No hace falta (f = 0). `productos/detalle/{codigoBarras}` pesa 260 KB por las imágenes.

## Propuesta

### Escalón elegido: b, API JSON con HTTP impersonado y `Referer` (f = 0)

SafeLine bloquea por huella TLS y headers, no por ritmo ni por cookies. Con `impersonate="chrome"`,
`Referer` y `Accept: application/json` la API responde siempre.

### Estrategia de cobertura

El listado por categoría no sirve para cobertura (tope de 50 sin paginación). La única vía es la
búsqueda:

1. **Consultas:** lista de moléculas, tomada de la primera palabra de `Molécula` en el catálogo NDF
   (`dim_ndf`, unas 1,770 sin contar sales como "clorhidrato" o "sulfato"), más los 15
   departamentos por `categorias/{id}` para lo que no es medicamento.
2. Si una consulta llega a 100, partirla agregando una segunda palabra (concentración o forma:
   `metformina 850`, `metformina glibenclamida`) hasta que baje de 100.
3. Tratar el 404 sin cuerpo como "sin resultados", no como error.
4. Deduplicar por `codigoBarras` y descartar `imagen` al leer la respuesta.
5. **Cobertura por corrida:** no hay total contra el cual medir. Se reporta el número de únicos y
   se compara contra la corrida anterior.
6. **Ritmo:** 1 petición cada 2 s (C = 1). El WAF no limitó, pero el sitio es de una institución
   pública y cada búsqueda baja varios MB.

### Presupuesto (sección 5)

Supuestos: unas 1,800 consultas (la mitad 404 rápidos), f = 0, Z = 1, C = 1, L = 1.6 s con
resultados y 0.5 s sin ellos (medidas), d = 2 s, r = 0.05.

| Alcance | Productos | Peticiones R | Horas H | Transferencia | Semáforo |
| --- | --- | --- | --- | --- | --- |
| Lo del legado (50 por departamento) | 612 | 15 | < 0.01 h | ~40 MB | ✅ |
| Medicamentos por moléculas + departamentos | ~5,000–13,000 (estimado) | ~1,800 | ~1.6 h | ~1.5–2.5 GB | 🟡 |

El tiempo cabe en una corrida, pero la transferencia es alta por las imágenes en base64, que la
API no deja omitir. Si se vuelve un problema, se puede bajar a C = 1 con d = 3 s y repartir en dos
noches.

### Riesgos

- **Términos de uso:** prohíben de forma explícita descargar, almacenar y uso comercial, y el WAF
  declara que el sitio está protegido contra bots. Es una institución pública. **Escalar a Aldo.**
- **Cobertura sin total:** la búsqueda no da conteos y el estimado de N es grueso. Una molécula
  que no esté en la lista no se captura.
- **SafeLine:** hoy basta con huella y Referer. Si sube el nivel del desafío (`level: "2"` en la
  página de bloqueo), habría que pasar al escalón d con navegador para resolver el CAPTCHA, lo
  cual no conviene hacer.
- **Transferencia:** unos 128 KB por producto por la imagen en base64.
- **Tope de 100 en la búsqueda:** sin aviso; el spider debe partir la consulta cuando llegue a 100.
- **404 = sin resultados:** si el spider lo trata como error, reintenta de más.
