# AXIOM - Precios

Pipeline ELT de precios de medicamentos en ecommerce mexicanos (farmacias y supermercados):
scraping por tienda, histórico en Google Cloud, modelado con dbt sobre BigQuery.

## Arquitectura

```
extract/  →  ./salida/data/*.csv  →  load/  →  GCS (raw → bronce)  →  BigQuery (external table)  →  transform/ (dbt)
```

- **`extract/`** — ~30 scrapers, uno por tienda. Fase 1 (URLs de categoría) + fase 2 (precio/SKU/imagen por producto).
- **`load/`** — ingesta idempotente del histórico a GCS y BigQuery (raw → bronce).
- **`transform/`** — dbt sobre la external table `precios_bronce.precios_ext`. Staging y silver
  (`precios`, `precios_cuarentena`) listos; gold y el matching contra el catálogo NDF
  (`entity_resolution/`), pendientes.

## Estructura

```
.
├── extract/          # scraping, proyecto uv propio
├── load/              # ingesta a Google Cloud, proyecto uv propio (con tests)
├── transform/          # dbt (transform/dbt/precios) + entity_resolution (pendiente)
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

Siempre desde la raíz del repo:

```bash
# extract — correr un scraper (fase 1 y 2)
uv run --project extract extract/urls/urls_scraping_soriana.py
uv run --project extract extract/detalle/scraping_detalle_soriana.py

# load — subir el histórico y ver el estado del manifest
uv run --project load python -m precios_load.cli ingesta
uv run --project load python -m precios_load.cli estado

# transform — correr y testear los modelos dbt
uv run --project transform dbt build --project-dir transform/dbt/precios --profiles-dir transform/dbt/precios
```

