# swedish-el-oss

Open-source rebuild of the Swedish electricity price platform.
APIs → raw (Postgres) → dbt bronze/silver/gold → sklearn forecast → static site.

Stack: Python ingest, PostgreSQL 16, dbt-core + dbt-postgres, scikit-learn,
Apache ECharts, Metabase (internal). Runs on macOS via launchd at 20:00.

## Layers
- `ingest/`  7 API sources → `raw.*` tables (idempotent on `input_file_name` + `file_modification_time`)
- `dbt/`     bronze (7) / silver (7) / gold (6) models — full refresh each run
- `ml/`      day-ahead price forecast + bill + evidence → `gold.price_forecast*`
- `site/`    `build_site.py` → `docs/` (GitHub Pages)

## Data model & data dictionary
Each layer's tables and columns are documented in its own README:

| layer | folder | what's there |
|---|---|---|
| **raw** | [`raw/README.md`](raw/README.md) | verbatim API responses (7 sources + the SMHI metobs archive) |
| **bronze** | [`dbt/models/bronze/README.md`](dbt/models/bronze/README.md) | raw payload parsed into typed columns |
| **silver** | [`dbt/models/silver/README.md`](dbt/models/silver/README.md) | cleaned + conversions (spot → SEK/kWh, consumer prices, FX, gas, weather, hydro) |
| **gold** | [`dbt/models/gold/README.md`](dbt/models/gold/README.md) | dimensions, `fact_daily` (price + bill + weather), gas, drivers, thermostat feature table |
| **ml** | [`ml/README.md`](ml/README.md) | `price_forecast`, `price_forecast_summary`, `price_model_evidence` |

Key formulas (full detail in the layer READMEs):
- **Spot:** `price_sek_kwh = value (EUR/MWh) / 1000 × eur_sek_rate`
- **Bill:** `total_consumer_sek_kwh = (spot + energy tax + grid fee) × 1.25` (25 % VAT)
- **Gas:** `gas_price_sek_kwh = gas_price_sek_mmbtu / 293.071`

## Setup
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env`  — add `ENTSOE_TOKEN` + `EIA_API_KEY`
4. `createdb swedish_el`
5. `dbt build`

Site: https://mlinggar.github.io/swedish-el-oss/
