# swedish-el-oss

Open-source rebuild of the Swedish electricity price platform.
APIs -> raw (Postgres) -> dbt bronze/silver/gold -> sklearn forecast -> static site.

Stack: Python ingest, PostgreSQL 16, dbt-core + dbt-postgres, scikit-learn,
Apache ECharts, Metabase (internal). Runs on macOS via launchd at 19:00.

## Layers
- ingest/   7 API sources -> raw.* tables (idempotent on input_file_name + file_modification_time)
- dbt/      bronze (7) / silver (7) / gold (6) - full refresh each run
- ml/       day-ahead price forecast + bill + evidence -> gold.price_forecast*
- site/     build_site.py -> docs/ (GitHub Pages)

## Setup
1. python3 -m venv .venv && source .venv/bin/activate
2. pip install -r requirements.txt
3. cp .env.example .env   # add ENTSOE_TOKEN + EIA_API_KEY
4. createdb swedish_el
5. dbt build

Site: https://mlinggar.github.io/swedish-el-oss/
