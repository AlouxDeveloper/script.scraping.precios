# load/: ingestion to GCS and BigQuery

Reply to the user in Spanish; code and comments in Spanish (see root `CLAUDE.md`).

## Commands (always from the repo root)

```bash
cd load && uv sync
uv run --project load python -m precios_load.cli plan              # dry-run, touches nothing
uv run --project load python -m precios_load.cli ingesta           # raw + bronce, records the manifest
uv run --project load python -m precios_load.cli ingesta-v2        # Scrapers 2.0 runs -> bronce P1 (+ _corridas_scraping)
uv run --project load python -m precios_load.cli catalogos         # salida/catalogos/dim_ndf.xlsx -> bronce Parquet
uv run --project load python -m precios_load.cli catalogos-puente  # puente_aportador.txt + CVE_APORTADOR_NOMBRE.xlsx -> bronce
uv run --project load python -m precios_load.cli bq-setup          # creates/replaces precios_ext, ndf_ext, puente_aportador_ext
uv run --project load python -m precios_load.cli estado            # manifest summary
uv run --project load pytest load/
```

`load/` aborts with a clear message if it is not run from the repo root. Do not set
`quota_project_id` in ADC: the integration tests get a 403 and are skipped.

## History flow

```
./salida/data/2026/<MM_mes>/*.csv        (extract/ output, listed in load/config/archivos.yml)
      │  cli.py ingesta
      ▼
gs://raw_precios_bitek/precios/tienda=<slug>/anio_mes=<YYYY-MM>/<archivo>.csv   ← CSV byte for byte, only up to 2026-08
      │  bronce.escribir  (normalizes to 26 typed columns, keeps the *_raw)
      ▼
gs://bronce_precios_bitek/precios/tienda=<slug>/anio_mes=<YYYY-MM>/<archivo>.parquet
      │  cli.py bq-setup
      ▼
precios_bronce.precios_ext   BigLake external table, hive-partitioned; sees a new Parquet instantly
      │  (from here on: transform/)
```

## Scrapers 2.0 flow (`precios_v2`, variant P1)

```
./salida/data_v2  or  gs://raw_precios_bitek/precios_v2     (written by scrapers/, no archivos.yml)
  tienda=<slug>/anio_mes=<YYYY-MM>/corrida=<corrida_id>/parte-NNNN.parquet + _corrida.json
      │  cli.py ingesta-v2 [--origen ...]   (precios_v2.py)
      ▼
gs://bronce_precios_bitek/precios/tienda=<slug>/anio_mes=<YYYY-MM>/<corrida_id>_parte-NNNN.parquet
      (same prefix as the history: precios_ext reads both)
```

- Discovery by convention. Only `estado = completa` runs reach bronce, and only if every part's
  MD5 matches `_corrida.json`. Parts skip raw (already typed and validated by the contract).
- Manifest: one row per part, `ruta_origen = precios_v2/<run folder>/<part>`, variant `P1`.
- Every `_corrida.json` (partial and aborted too) goes to `precios_ops._corridas_scraping`,
  append-only by `(corrida_id, md5_json)`; the current row of a run is its latest `cargado_en`.
- P1 = the 26 history columns + 12 nullable contract columns at the end. `fecha_captura` is the
  Mexico City wall time labeled UTC, like the history; the real UTC is `capturado_en_utc`.
- `precios_ext` has an **explicit schema** (`bq.tipo_sql` over `precios_v2.ESQUEMA_P1`).
  Inferred, BigQuery takes the alphabetically last file (a history one) and drops the P1
  columns. Old Parquet files read NULL in the columns they lack (verified 2026-10-07). Lists
  read as `STRUCT<list ARRAY<STRUCT<element>>>`, maps as `STRUCT<key_value ARRAY<...>>`.

## Catalog flow (separate from the history)

```
./salida/catalogos/dim_ndf.xlsx          (one sheet, 23 columns; Aldo drops it there by hand)
      │  cli.py catalogos  (catalogos.py: renames to 17 snake_case columns, all STRING)
      ▼
gs://bronce_precios_bitek/catalogos/ndf/dim_ndf.parquet     ← does NOT go through raw
      │  cli.py bq-setup
      ▼
precios_bronce.ndf_ext   external table, a single replacement Parquet, no partitions
```

The crosswalk (`catalogos-puente`) follows the same pattern into `puente_aportador_ext`. Aldo
renames the cut's TXT (`Puentes por Aportador <fecha>.txt`) to `puente_aportador.txt` first.

## Decisions

- **`tienda`** is the stable slug from `archivos.yml` (`walmart`, `chedraui`), never the CSV
  content. The scraper's literal value (`12`, `Soriana`, or empty) is kept in `tienda_raw`.
  Partition and slug come from the folder.
- **Idempotency** lives in `precios_ops._ingesta_manifest`: append-only, one row per file
  ingestion, state = the row with the highest `version`. Running `ingesta` twice uploads
  nothing new.
- **Catalogs have no manifest and skip raw.** A catalog is a full replacement snapshot:
  running `catalogos` twice overwrites the same object, which is correct.
- **The catalog Parquet is all STRING on purpose.** Typing belongs in dbt (`ndf_id` without
  leading zeros, `fecha_lanzamiento` as `YYYYMM` with the `190012` sentinel). The
  `Cve Sal1..6` columns are dropped.
- **The raw bucket is a frozen archive** (Dec-2025 to Aug-2026). From 2026-09 on, `ingesta`
  writes only the bronce Parquet (`ULTIMO_MES_RAW` in `config.py`; the manifest row has
  `uri_raw` NULL). A parser bug is fixed by regenerating bronce from raw (up to Aug-2026) or
  re-deriving in dbt from the `*_raw` columns; the past is never re-scraped.
- **One batch per store and month.** When a month has several scraping runs, only one goes
  into `salida/data` and `archivos.yml`; the rest live in `salida/_corridas/<YYYY-MM>/`.
  The `mart_` models keep the lowest price of the month, so loading every run would make
  that month look cheaper than months captured once.
- Config lives in `load/config/gcp.yml` (infrastructure) and `load/config/archivos.yml` (file
  inventory). A month is added to `archivos.yml` only after it closes.
