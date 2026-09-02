# Bitek - Precios

```
bitek-precios/
├── .gitignore
├── .python-version
├── README.md
├── Makefile
├── pyproject.toml              # uv workspace root 
├── uv.lock
│
├── extract/                    # E — scraping, proyecto uv AISLADO 
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── urls/                   # 11 scripts fase 1
│   └── detalle/                # 15 + 4 scripts fase 2 (incl. variantes scraping_data_*)
│
├── load/                       # L — miembro del workspace raíz
│   ├── pyproject.toml
│   └── tests/
│
├── transform/                  # T — dbt + entity resolution
│   ├── dbt/
│   │   └── precios/
│   │       ├── dbt_project.yml
│   │       ├── seeds/matching_manual_overrides.csv
│   │       └── models/{staging,intermediate,marts}/
│   └── entity_resolution/      # miembro del workspace raíz
│       ├── pyproject.toml
│       ├── src/bitek_matching/
│       │   ├── run_matching.py
│       │   ├── farma/          # paso 1-2: regex + rapidfuzz
│       │   └── no_farma/       # placeholder fase 2
│       └── tests/
│
├── salida/                      # 🔒 intocable — output del extract
├── config/
```
