# transform/: dbt project (transform/dbt/precios)

Reply to the user in Spanish; code, SQL comments, docstrings and dbt descriptions in Spanish
(see root `CLAUDE.md`).

## Commands (always from the repo root)

```bash
D="--project-dir transform/dbt/precios --profiles-dir transform/dbt/precios"
uv run --project transform dbt parse $D                  # fast; a hook runs it after every .sql/.yml edit
uv run --project transform dbt build $D --select <modelos>
uv run --project transform dbt test  $D --select <modelos>
uv run --project transform dbt docs generate $D          # the home page is models/overview.md
```

Profile `precios`, BigQuery target through ADC, no `quota_project_id`.

**Select explicitly.** Do not run `+dim_producto` or `int_producto+` carelessly: they pull in
the whole embeddings and vector-search chain.

## dbt conventions

Check current docs through context7 before writing config or macros. The guiding principle is DRY.

- **Never hardcode a table name.** `ref()` and `source()` build the DAG.
- **Jinja for repetition, not cleverness.** Shared logic goes to `macros/`. The compiled SQL in
  `target/compiled` must stay readable.
- **Packages before custom code:** `dbt_utils` (dates, strings, pivots, `expression_is_true`,
  `unique_combination_of_columns`) and `dbt_expectations`.
- **SQL for 90% of the modeling.** Python models only for what SQL cannot do.
- **A model without schema tests is not finished.** Each model has its `_<modelo>.yml` with
  descriptions (in Spanish) and tests, and a `{# #}` docstring explaining the *why*.
- Direction, not built yet: `elementary`, `cosmos`/`dagster-dbt`, Slim CI
  (`state:modified+ --defer`).

## BigQuery naming

A badly named object outlives the whole history, so decide the name before writing the model.

- `snake_case`, lowercase, Spanish, no accents or `ñ`.
- Datasets `precios_<capa>`: `precios_bronce`, `precios_silver`, `precios_gold`, `precios_ml`,
  `precios_ops`. The layer goes in the dataset, never in the table name.
- Tables and views in singular, at the row grain (`dim_producto`). `precios` and
  `precios_cuarentena` are the historical exception.
- `_ext` suffix for external tables.
- Columns never start with `_TABLE_`, `_FILE_`, `_PARTITION` or `_ROW_TIMESTAMP`. A leading
  underscore is reserved for lineage (`_archivo_origen`, `_fila_num`, `_ingestado_en`).
- No SQL reserved words as column names.
- Name the partition column after what it is (`mes`, `fecha_key`).
- Unit suffix when ambiguous (`_pct`, `_mxn`, `_ms`); never a type suffix (`_str`, `_int`).
- Booleans: `es_*`, `tiene_*` or `*_ok`. `_raw` suffix for the unparsed original next to its
  derived column.

## Dimensional model (Kimball)

- `dim_<entidad>` and `fact_<proceso>`. It is `fact_`, **not** `fct_`.
- dbt layer prefixes: `stg_` (1:1 view of the source), `int_` (intermediate), `dim_`/`fact_`
  (gold), `rev_` (operational review view).
- Surrogate key `<entidad>_key`, business natural key `<entidad>_id`. Never a bare `id` or `pk`.
- An FK keeps the name of its dimension's PK, so joins are `USING (producto_key)`.
- `_actual` suffix for SCD1 attributes (`url_producto_actual`).
- Measures carry the business name (`precio_lista`, `precio_oferta`). Derived measures live in
  the consumption layer, not in the fact.
- Counts and durations: `<sustantivo>_<unidad>` (`dias_observados`).
- BigQuery does not enforce PK/FK: dbt tests are the contract (`unique`, `not_null`,
  `relationships`).

## Architecture

```
precios_bronce.precios_ext → stg_precios (view) → precios_silver.precios / precios_cuarentena
precios_bronce.ndf_ext → stg_ndf → dim_ndf
precios_bronce.puente_aportador_ext → stg_puente_aportador → dim_puente_aportador

precios_silver.int_producto   product + ndf_id from aportadores / ean_cruzado
      │  models/ml/  (schema precios_ml)
      ▼
int_texto_er → emb_texto (paid bank) → emb_producto / emb_ndf (merge; TREE_AH on emb_ndf)
      → int_candidatos_producto (top-10) → int_candidato_evaluado → int_match_ndf
        (rule in macros/decision_vectorial.sql; rev_er_calibracion sweeps tau)
      │                                         │
      ▼                                         ▼
precios_gold.dim_producto                precios_silver.ndf_cuarentena (method 3 input)
      ▼
precios_gold.fact_precios (grain producto_key, fecha_key) + dim_tienda, dim_fecha, dim_ndf
```

**`models/overview.md` is the source of truth** for the full flow, current metrics, the monthly
load runbook and how to switch back to `v1`. Do not copy numbers here; they go stale.

## Rules not to re-derive

**Silver and gold**
- `motivo_descarte` (`SIN_DESCRIPCION`, `SIN_PRECIO`, `SIN_SKU`, `DUPLICADO`) is assigned once
  in `stg_precios`. `precios` + `precios_cuarentena` are the same universe without losing rows
  (`assert_ninguna_fila_perdida`).
- `sku` imputation from `url_producto` applies **only to aurrera** (99.99% verified). The same
  pattern gives 0% on soriana: do not generalize without verifying.
- `precio_oferta` is `NULL` when there is no real discount, **never `0`**.
- `ndf_id` has no leading zeros, on both `dim_ndf` and the crosswalk.
- `dim_ndf.producto` is the catalog brand; `dim_producto.producto` is the store listing name.
- `tienda_key` is never reused.
- `fact_precios` dedups `(producto_key, fecha_key)`: silver is not unique.

**Crosswalk and ndf_id assignment**
- `dim_puente_aportador` grain is `(tienda_key, sku, ndf_id)`: ambiguity is kept, not guessed.
  Its `sku` is trimmed and padded to 15 digits; `int_producto` crosses it through a temporary
  `sku_cruce`. ~41% of its `ndf_id` do not exist in `dim_ndf` (the `8989898` sentinel or ids
  missing from the cut): its FK is logical and only a `warn`.
- `match_method` accumulates and never overwrites: `aportadores` → `ean_cruzado` → `vectorial`.
  `ean_cruzado` requires 8+ digits (below that, precision is 0-17%).

**Vector entity resolution (`precios_ml`)**
- The `emb_texto` bank is keyed by text hash. **Never run it with `--full-refresh`** (a macro
  aborts it). To regenerate a generation, `DELETE` by `modelo`, and Aldo runs that.
- `emb_producto`/`emb_ndf` are incremental `merge` so they are never recreated. Only `emb_ndf`
  has a `TREE_AH` index, created by a `post_hook` if missing. After a `--full-refresh`, coverage
  sits at 0% for ~10 min; `int_candidatos_producto` warns before falling back to brute force.
- BigQuery stores a NULL ARRAY as `[]`: vector coverage is checked with
  `assert_emb_*_cobertura` (key + hash), never with `not_null`.
- The `ml/` models read `int_producto`, never `dim_producto`: reading `dim_producto` would
  create a cycle.
- The rule lives in `macros/decision_vectorial.sql` and is shared by production and
  calibration. `rev_er_calibracion` does **not** apply `cuarentena_forzada`, which was decided
  on orphans and would distort tau.
- The `tau` values belong to text `v4`. Changing the text requires recalibrating on the
  calibration split. The holdout has never been touched.
- `TREE_AH` is approximate: the `vectorial` count moves by a few dozen between index rebuilds.
  That is not a regression.

`transform/entity_resolution/` holds the manual audit scripts (`auditar_muestra.py`,
`auditar_huerfanos.py`) and the one-time infrastructure DDL in `sql/`, in this order:
`dataset_precios_ml.sql` → `conexion_vertex.sh` → `modelo_emb_gemini.sql`.
