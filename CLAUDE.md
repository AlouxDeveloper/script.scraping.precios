# script.scraping.precios

## Language

- **Always reply to the user in Spanish**, including plans, summaries and questions.
- Code, comments, docstrings, prints, identifiers, commit messages and project docs
  (`overview.md`, dbt descriptions) are written in **Spanish**. Keep that convention in new code.
- These `CLAUDE.md` files are in English on purpose; that does not change the two rules above.

## What this repo is

ELT pipeline for medication prices on Mexican e-commerce sites (pharmacies and supermarkets).
Three modules, each with its own `CLAUDE.md` that loads when you work inside it:

- **`extract/`**: ~30 scrapers, one per store. Writes CSVs to `./salida/data/`.
- **`load/`**: ingests the history into GCS (raw → bronce) and exposes it in BigQuery.
  Own uv project (`precios-load`, Python ≥3.13) with real integration tests.
- **`transform/`**: dbt project in `transform/dbt/precios/`: staging, silver, gold (star schema)
  and `precios_ml` (vector entity resolution that assigns `ndf_id` to each store product).

`README.md` describes the real repo layout. There is no root uv workspace and no Makefile.
`salida/` is gitignored local data (CSVs, catalogs, audits, exports).

## Commands

No Makefile, linter or formatter. `extract/` has no tests; `load/` does (pytest against real
BigQuery/GCS, skipped without ADC credentials).

```bash
# ALWAYS from the repo root: script paths are relative to it (./data, ./salida).
uv run --project extract extract/detalle/scraping_detalle_soriana.py
uv run --project load python -m precios_load.cli plan        # dry-run
uv run --project load pytest load/
uv run --project transform dbt build --project-dir transform/dbt/precios --profiles-dir transform/dbt/precios
uv run --project transform dbt parse --project-dir transform/dbt/precios --profiles-dir transform/dbt/precios
```

## Code style (Python)

- PEP 8 naming with Spanish names: `snake_case` functions/variables, `MAYUSCULAS` module
  constants, `CapWords` classes; 4-space indent; lines ≤ 79-99 chars; imports grouped
  stdlib / third party / local.
- PEP 257 docstrings: module docstring on every new script (which store/phase, how to run it);
  one-line docstring when the purpose is obvious, summary + detail when there are several
  parameters or edge cases.
- Comments explain the *why* (a decision, a workaround, a fragile selector, an edge case),
  never the *what*. Comment anti-bot logic, `sleep`s, preserved legacy formats and assumptions
  about a store's HTML. Full sentences; keep comments in sync with the code.
  Mark pending work with `# TODO:` / `# FIXME:`.
- Before finishing any task that touches code, check PEP 8 / PEP 257 and these comment rules.

**Closing a task:** once the code is approved, write the missing documentation (docstrings,
module comments, *why* comments). The ponytail plugin keeps code and chat terse, but it does
not apply to docstrings or documentation the closing step requires: write those in full prose.

## Git

- Working branch: `dev`. Conventional Commits in Spanish.
- **Never commit.** No `git add`, `git commit`, `git push`, `git reset`, `git rebase`, or
  anything that rewrites history, unless the user explicitly asks. Leave changes in the working
  tree and suggest the commit message in chat. A hook enforces this.
- Commit messages: **280 characters max** in total (subject + body).

## Destructive actions in the cloud

- Never delete in BigQuery or GCS (`bq rm`, `DROP`, `DELETE`, `TRUNCATE`). Give Aldo the exact
  commands to run manually. A hook enforces this.
- Never run `emb_texto` with `--full-refresh`: it holds paid embeddings (see `transform/CLAUDE.md`).

## Tools

- **context7**: before writing dbt config, macros or BigQuery SQL (VECTOR_SEARCH,
  AI.GENERATE_EMBEDDING, vector indexes, MERGE), check current docs through context7
  (dbt-core, dbt-bigquery, BigQuery) instead of relying on memory.
- **agent-skills**: use `debugging-and-error-recovery` for a failing scraper or dbt build,
  `code-review-and-quality` before suggesting a commit message, `documentation-and-adrs` for
  design decisions, `source-driven-development` together with context7.
- **Subagents**: use `Explore` only for wide searches (e.g. across the 30 scrapers). Do the
  rest inline.
- **Linear** (project `precios`, issues `ALD-xx`) is the plan; **Notion** page 🧭 AXIOM holds
  design docs and reports. Publish there only when asked.

## Writing for Monday (stories and activities)

Monday is the team board (Axiom), read by people without access to Linear or the repo. Every
text for Monday is in Spanish and in business language: **never mention Linear, issue IDs
(ALD-xx), or table/model names**. Points 1-5, priority `Baja` / `Media` / `Alta`. One story per
business goal, not per technical task.

**User story**, fields in this order:

1. **Título:** short (e.g. "Cobertura base del portafolio Sanfer").
2. **Historia:** "Como <usuario>, puedo <hacer> para <beneficio>". The user is the *analista de
   Sanfer* if it shows in the dashboard, or the *equipo de datos* for internal work; never name
   the NDF to the analyst.
3. **Criterios de aceptación:** short, verifiable bullets.
4. **Epic:** one or two words.
5. **Puntos:** 1 to 5.
6. **Prioridad:** Baja, Media or Alta.

**Activity** (task or sub-item of a story): a short name, plus
**Descripción** (max 150 words: what, why, dependencies) and **Entregable / verificación**
(what is done and how it is checked).
