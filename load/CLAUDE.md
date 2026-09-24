# load/: ingestion to GCS and BigQuery

Reply to the user in Spanish; code and comments in Spanish (see root `CLAUDE.md`).

## Commands (always from the repo root)

```bash
cd load && uv sync
uv run --project load python -m precios_load.cli plan              # dry-run, touches nothing
uv run --project load python -m precios_load.cli ingesta           # raw + bronce, records the manifest
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
gs://raw_precios_bitek/precios/tienda=<slug>/anio_mes=<YYYY-MM>/<archivo>.csv   ← CSV byte for byte
      │  bronce.escribir  (normalizes to 26 typed columns, keeps the *_raw)
      ▼
gs://bronce_precios_bitek/precios/tienda=<slug>/anio_mes=<YYYY-MM>/<archivo>.parquet
      │  cli.py bq-setup
      ▼
precios_bronce.precios_ext   BigLake external table, hive-partitioned; sees a new Parquet instantly
      │  (from here on: transform/)
```

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
- **The raw bucket is a frozen archive** (Dec-2025 to Sep-2026). A parser bug is fixed by
  regenerating bronce from raw or re-deriving in dbt from the `*_raw` columns; the past is
  never re-scraped.
- Config lives in `load/config/gcp.yml` (infrastructure) and `load/config/archivos.yml` (file
  inventory). A month is added to `archivos.yml` only after it closes.
