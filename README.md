# AXIOM - Precios

Pipeline ELT de precios de medicamentos en ecommerce mexicanos (farmacias y supermercados):
scraping por tienda, histórico en Google Cloud, modelado con dbt sobre BigQuery.

## Arquitectura

```
extract/  →  ./salida/data/*.csv  →  load/  →  GCS (raw → bronce)  →  BigQuery (external tables)  →  transform/ (dbt: silver → gold)
```

- **`extract/`** — ~30 scrapers, uno por tienda. Fase 1 (URLs de categoría) + fase 2 (precio/SKU/imagen por producto).
- **`load/`** — ingesta idempotente del histórico a GCS y BigQuery (raw → bronce), más el
  comando `catalogos` que sube el catálogo NDF (solo a bronce).
- **`transform/`** — dbt sobre las external tables `precios_bronce.precios_ext` y
  `precios_bronce.ndf_ext`. Staging, silver (`precios`, `precios_cuarentena`) y gold
  (star schema: `fact_precios` + `dim_tienda`, `dim_fecha`, `dim_producto`, `dim_ndf`)
  listos y testeados. Pendiente: `entity_resolution/` (asignar `ndf_id` a cada producto
  de tienda por matching contra el catálogo NDF).

### Flujo del catálogo NDF

Aparte del histórico de precios, con su propio comando:

```
./salida/catalogos/dim_ndf.xlsx  →  load/ (catalogos)  →  gs://…/catalogos/ndf/dim_ndf.parquet  →  ndf_ext  →  stg_ndf  →  dim_ndf
```

No pasa por `raw` ni lleva manifest: un catálogo es un snapshot de reemplazo completo.

## Estructura

```
.
├── extract/          # scraping, proyecto uv propio
├── load/              # ingesta a Google Cloud, proyecto uv propio (con tests)
├── transform/          # dbt (transform/dbt/precios): staging, silver, gold; + entity_resolution (pendiente)
└── salida/              # salida de extract/, en .gitignore
```

## Requisitos

Python 3.13+, [`uv`](https://docs.astral.sh/uv/), credenciales de Google Cloud (ADC) para
`load/` y `transform/`.

## Instalación

Cada módulo (`extract/`, `load/`, `transform/`) es un proyecto `uv` independiente, con su
propio `pyproject.toml` y entorno virtual. Instala las dependencias de cada uno antes de
correrlo, siempre desde la raíz del repo:

```bash
cd extract && uv sync && cd ..
cd load && uv sync && cd ..
cd transform && uv sync && cd ..
```

### Variables de entorno

Copia `.env.example` a `.env` en la raíz del repo y llena los valores reales. `.env` está en
`.gitignore`, nunca se sube:

```bash
cp .env.example .env
```

Usadas hoy:

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — alerta de Telegram que manda
  `extract/detalle/monitoreo.py` cuando un scraper detecta bloqueo o captcha repetido.

## Uso

Siempre desde la raíz del repo. El flujo completo, en orden:

```bash
# 1. extract — correr un scraper (fase 1 y 2)
uv run --project extract extract/urls/urls_scraping_soriana.py
uv run --project extract extract/detalle/scraping_detalle_soriana.py

# 2. load — subir el histórico a GCS y BigQuery (raw → bronce), idempotente
uv run --project load python -m precios_load.cli plan       # dry-run
uv run --project load python -m precios_load.cli ingesta
uv run --project load python -m precios_load.cli estado     # estado del manifest

# 3. load — subir el catálogo NDF (deja antes el XLSX en ./salida/catalogos/dim_ndf.xlsx)
uv run --project load python -m precios_load.cli catalogos

# 4. load — crear/reemplazar las external tables (precios_ext y ndf_ext)
uv run --project load python -m precios_load.cli bq-setup

# 5. transform — construir y testear silver + gold
uv run --project transform dbt build --project-dir transform/dbt/precios --profiles-dir transform/dbt/precios

# 6. transform — documentación navegable (portal web local con DAG y linaje)
uv run --project transform dbt docs generate --project-dir transform/dbt/precios --profiles-dir transform/dbt/precios
uv run --project transform dbt docs serve    --project-dir transform/dbt/precios --profiles-dir transform/dbt/precios
```

`load/` y los comandos dbt abortan o escriben en el lugar equivocado si no se corren
desde la raíz del repo.

