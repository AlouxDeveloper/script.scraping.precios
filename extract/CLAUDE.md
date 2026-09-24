# extract/: scrapers

Reply to the user in Spanish; code and comments in Spanish (see root `CLAUDE.md`).

## Two-phase pipeline

```
./data/*.xlsx           (category URLs, curated by hand, NOT in the repo)
      │  extract/urls/*.py        ← phase 1: walks categories, paginates, collects product URLs
      ▼
./salida/urls/*.csv     (URL + name per product)
      │  extract/detalle/*.py     ← phase 2: visits each product, extracts price/SKU/image
      ▼
./salida/data/2026/<MM_mes>/scraping_detalle_<tienda>.csv
```

- `data/` is not in the repo: without the category `.xlsx` the script aborts with
  `❌ No se encontró el Excel`.
- Single-step exceptions (read `./data/*.xlsx` and write detail directly):
  `scraping_detalle_alsuper.py`, `scraping_data_isseg.py`, `scraping_detalle_guadalajara.py`.
- Always run from the repo root: every path is relative to it.
- Most Selenium scrapers run with a visible Chrome window. Only chedraui, fesa, soriana, gi,
  comer and farmatodo use `--headless`. On WSL or a server without a display, add headless or
  a virtual display.
- `detalle/monitoreo.py` (logging + Telegram alerts) exists, but no scraper imports it yet.

## Output schema

Phase 2 converges on 8 columns:

```
SKU, URL_PRODUCTO, Producto, Precio_Actual, Precio_Oferta, URL_IMAGEN, Fecha_Hora_Captura, Tienda
```

Existing variants must be respected. Historical CSVs were written this way, so do not
"normalize" them without agreement:

- `scraping_data_isseg.py` and `scraping_data_sanpablo.py` use uppercase and `FECHA` instead of
  `Fecha_Hora_Captura`.
- `scraping_detalle_similares.py` and `scraping_detalle_guadalajara.py` use `URL_Producto` and
  `Precio_Normal`.
- `Tienda` is inconsistent by history. Some scripts write the store name (`"Soriana"`,
  `"Farmacias Yza"`); others write a numeric id as a string (`"2"` Benavides, `"3"` Ahorro,
  `"12"` Walmart, `"16"` Aurrera, `"17"` ISSEG, `"22"` Alsuper). `load/` takes the store from
  the folder, not from this column.
- Phase-1 CSVs are not normalized either. The most common header is `Producto,URL_PRODUCTO`,
  but Walmart and Aurrera use `Nombre,URL`, San Pablo uses `;` as separator, and others add
  `Categoria`/`SKU`.

## Scraper conventions

Every new script follows the existing pattern:

- **Config in UPPERCASE constants at the top** (`CSV_INPUT`/`EXCEL_CATEGORIAS`, `CSV_OUTPUT`,
  `TIENDA`, `FIELDNAMES`). No CLI or argparse: switching month or store means editing them.
- **The output path hardcodes the month** (`./salida/data/2026/09_septiembre/...`). At the start
  of each monthly run, update `CSV_OUTPUT` in every script. Folders `01_enero`..`12_diciembre`
  already exist.
- **Incremental append + `f.flush()`** row by row, with `csv.DictWriter`. Call `writeheader()`
  only if the file is missing or empty. Never accumulate everything in memory to write at the end.
- **Resume:** on start, read the existing output CSV and load a `set` of processed URLs or SKUs
  to skip. Preserve this: runs are long and get interrupted.
- **Never abort for one product:** `try/except` per item, `continue`, and default price
  `"0.00"` when parsing fails.
- `os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)` before opening the output.

## Choosing an anti-bot technique

When adding or fixing a store, pick what already works in the repo:

- **Direct JSON API** (preferred when it exists): `requests` for Alsuper, Ahorro, Benavides and
  Yza; `curl_cffi` (TLS fingerprint impersonation) for ISSEG and San Pablo, which sit behind a
  WAF. Both need a full `HEADERS` dict with `User-Agent`, `Referer`, `Origin` and `Sec-*`.
- **Standard Selenium** (`webdriver_manager` + `ChromeDriverManager().install()`): most VTEX
  stores (Chedraui, Soriana, La Comer, Farmatodo, Klyns, Yza, Similares, HEB, Gi, Farmalisto,
  Fesa, Guadalajara).
- **`undetected_chromedriver`**: only Walmart and Aurrera (aggressive detection) and the
  Chedraui listing.

Many stores are **VTEX**, so selectors repeat across scripts
(`.vtex-store-components-3-x-sellingPriceValue`,
`.vtex-product-identifier-0-x-product-identifier__value`, links ending in `/p`). Listings need
progressive scrolling to trigger lazy loading. Copy an existing VTEX script before writing one
from scratch.
