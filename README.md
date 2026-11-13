# swedish-el-oss

Open-source rebuild of the Swedish electricity price platform.
APIs → raw (Postgres) → dbt bronze/silver/gold → sklearn forecast → static site.

Stack: Python ingest, PostgreSQL 16, dbt-core + dbt-postgres, scikit-learn,
Apache ECharts, Metabase (internal). Runs on macOS via launchd at 20:00.

- **ingest/** 7 API sources → `raw.*` (idempotent on `input_file_name` + `file_modification_time`)
- **dbt/** bronze (7) / silver (7) / gold (6) — full refresh each run
- **ml/** day-ahead price forecast + bill + evidence → `gold.price_forecast*`
- **site/** `build_site.py` → `docs/` (GitHub Pages)

Site: https://mlinggar.github.io/swedish-el-oss/

## Setup
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env`  — add `ENTSOE_TOKEN` + `EIA_API_KEY`
4. `createdb swedish_el`
5. `dbt build`

---

# Data dictionary

Every table and column in the warehouse, what the value means, and how it is calculated.

**Layers:** `raw` → `bronze` → `silver` → `gold` (→ `ml`, written into `gold.price_forecast*`).
`raw` stores verbatim API responses, `bronze` parses them into typed columns, `silver` cleans
and conforms them, `gold` builds the business tables (dimensions, the daily fact, drivers, gas,
and the ML outputs).

## Conventions
- **Unit:** prices are **SEK/kWh** (kronor per kilowatt-hour) unless stated. Nord Pool spot
  arrives as **EUR/MWh**.
- **Conversion:** `price_sek_kwh = value (EUR/MWh) / 1000 × eur_sek_rate` (MWh→kWh, EUR→SEK).
- **Bill (what the consumer pays):** `total_consumer_sek_kwh = (spot + energy tax + grid fee) × 1.25`
  — 25 % VAT (`vat_rate`).
- **Currency:** `eur_sek_rate` is the ECB EUR→SEK rate, as-of carried forward to each date.
- **Time:** `ts_utc` is UTC; `ts_local` is `Europe/Stockholm`. `date_local` is the local date.
- **Idempotency:** `raw` rows are keyed on (`input_file_name`, `file_modification_time`);
  re-ingesting the same file replaces it. Downstream layers de-dup on `file_modification_time`.

---

## 1. raw layer — verbatim API responses

All `raw.*` API-dump tables share the same ingest envelope. Each row is one API response.

| column | type | meaning & value |
|---|---|---|
| `input_file_name` | text | Key/id of the source request (part of the idempotency key). |
| `file_modification_time` | timestamptz | Source timestamp of the response (part of the idempotency key; newest wins). |
| `load_tier` | text | Ingest run type: `historical` (backfill) or `daily`. |
| `payload` | jsonb | The raw API response body, stored verbatim. |
| `ingested_at` | timestamptz | When the row was written. |

**Tables:** `raw.raw_ecb` (ECB FX), `raw.raw_eia` (EIA gas), `raw.raw_entsoe` (ENTSO-E prices/
load/generation), `raw.raw_scb` (SCB consumer prices), `raw.raw_smhi_forecast` (SMHI weather
forecast), `raw.raw_smhi_hydro` (SMHI hydro discharge), `raw.raw_smhi_metobs` (SMHI weather
observations).

### raw.smhi_metobs_archive_rows
The SMHI observation **archive CSV** is parsed into rows here (a separate path from the JSON dumps).

| column | type | meaning & value |
|---|---|---|
| `source_file` | text | The archive file the row came from. |
| `file_modification_time` | timestamptz | Source timestamp (idempotency key). |
| `load_tier` | text | `historical` / `daily`. |
| `zone` | text | Bidding zone (SE1–SE4). |
| `parameter_code` | text | Observed parameter (e.g. `temp`, `wind_speed`, `precipitation`). |
| `station_id`, `station_name` | text | SMHI station identity. |
| `parameter_name`, `unit` | text | Human-readable parameter and unit. |
| `obs_date`, `obs_time` | text | Observation timestamp (as text in the source). |
| `value` | text | Observed value (text; typed downstream). |
| `quality` | text | SMHI quality flag. |

---

## 2. bronze layer — raw payload parsed to typed columns

Bronze extracts the `payload` JSON into typed columns. All bronze tables add the ingest envelope:
`source_file`, `load_tier`, `file_modification_time`, `extracted_at`.

### bronze.entsoe_points
One row per ENTSO-E data point (price / load / generation).

| column | type | meaning & value |
|---|---|---|
| `data_item_code` | text | ENTSO-E item (e.g. `ENERGY_PRICES` = day-ahead price). Mapped to `metric` in silver. |
| `business_dim` | jsonb | Business dimensions from the XML (e.g. `PRODUCTION_TYPE`, `CONTRACT_TYPE`). |
| `instance_attr` | jsonb | Instance attributes (e.g. `BIDDING_ZONE`). |
| `period_from`, `period_to` | text | The period the series covers. |
| `resolution` | text | Point resolution, e.g. `PT60M` (hourly). |
| `point_index` | integer | 1-based position within the period (→ `point_ts_utc`). |
| `point_ts_utc` | timestamptz | Timestamp of the point (UTC), derived from the period start + index × resolution. |
| `value_1`, `value_2` | text | Numeric values as text (e.g. price, or generation/secondary value). |

### bronze.scb_price_measures
One row per SCB consumer-price observation.

| column | type | meaning & value |
|---|---|---|
| `table_name` | text | SCB source table (e.g. `hushall`, `elnat`). |
| `dims` | jsonb | Dimensions (`Kundkategori`, `Avtalstyp`, `Elomrade`, `Viktat`…). |
| `period` | jsonb | The period the price applies to (e.g. `2024H1`, `2024M01`). |
| `measure_code` | text | SCB measure code (e.g. `000006WO`). Mapped to `measure_key` in silver. |
| `measure_text`, `measure_value` | text/jsonb | Human label and the value (öre/kWh). |

*(The other bronze tables — `ecb_fx_rates`, `eia_gas_prices`, `smhi_forecast_points`,
`smhi_hydro_observations`, `smhi_metobs_observations` — follow the same pattern: source keys +
the parsed measure values and dimensions.)*

---

## 3. silver layer — cleaned, conformed, derived

### silver.entsoe_timeseries  *(hourly spot / load / generation)*
De-duplicated, typed, converted to SEK.

| column | type | meaning & value |
|---|---|---|
| `bidding_zone` | text | SE1–SE4 (parsed from the source path). |
| `metric` | text | `day_ahead_price`, `load_forecast`, `actual_load`, `actual_generation` (from `data_item_code`). |
| `production_type`, `contract_type` | text | From `business_dim`. |
| `resolution` | text | e.g. `PT60M`. |
| `ts_utc`, `ts_local` | timestamptz / timestamp | Point time (UTC and `Europe/Stockholm`). |
| `value` | numeric | Raw value (EUR/MWh for prices; MW for load/generation). |
| `value_secondary` | numeric | Secondary value where the source has one. |
| `eur_sek_rate` | numeric | ECB EUR→SEK rate as-of `ts_utc` (from `fx_rates_daily`); fallback = earliest rate. |
| `price_sek_kwh` | numeric | **`value / 1000.0 × eur_sek_rate`** — the spot price in SEK/kWh (only for `day_ahead_price`). |
| `obs_year` | integer | Year of `ts_utc`. |

### silver.consumer_prices  *(SCB consumer prices, pivoted)*
Each row is one (table, category, period) with the price measures pivoted to columns.
`measure_code` → `measure_key`: `000006WO` handelspris, `000006WP` natpris, `0000070Q` elskatt,
`000006WQ` natpris_med_elskatt, `000006WR` moms, `000006WS` totalpris, `000003GO` elhandelspris,
`000006QI` elnatspris.

| column | type | meaning & value |
|---|---|---|
| `table_name` | text | `hushall` (household) or `elnat` (grid). |
| `customer_category` | text | e.g. `DA` (household), `1` (grid). |
| `contract_type`, `grid_area`, `weighting` | text | SCB dimensions (e.g. `viktat` = weighted). |
| `period_type` | text | `half_year` / `month` / `year` (from the period code). |
| `period_start` | date | Start date of the price period. |
| `period` | text | The period code (e.g. `2024H1`). |
| `*_ore_kwh` | numeric | Price in **öre/kWh** per measure (handelspris, natpris, elskatt, elhandelspris, elnatspris…). |
| `*_sek_kwh` | numeric | The same price in **SEK/kWh** = `*_ore_kwh / 100.0`. |

### silver.fx_rates_daily  *(ECB FX)*
`obs_date`, `currency` (e.g. `SEK`), `currency_denom`, `exr_type`, `rate` (units of currency per EUR),
`series_key`. Used for all EUR→SEK and USD→SEK conversion.

### silver.gas_prices_daily  *(EIA gas)*
`gas_date`, `gas_price_usd_mmbtu` (US$/MMBtu), `series`, `units`. Converted to SEK/kWh in gold.

### silver.weather_observations_hourly / weather_forecast_hourly  *(SMHI)*
Hourly weather per zone. Observations: `parameter_code`/`value` (temp, wind_speed, precipitation)
with `quality`. Forecast: `reference_time`, `air_temperature`, `wind_speed`, `wind_speed_of_gust`,
`precipitation_amount_mean`, `relative_humidity`, `cloud_area_fraction`, `lat`, `lon`.

### silver.smhi_hydro_observations_daily  *(SMHI hydro)*
`zone`, `station_*`, `parameter_code` (discharge), `value` (m³/s), `quality`.

---

## 4. gold layer — business tables

### gold.dim_calendar  *(date dimension, 2022–2030, one row per day)*

| column | type | meaning & value |
|---|---|---|
| `date_key` | integer | `YYYYMMDD` surrogate key. |
| `date_local` | date | The date. |
| `effective_month` | date | First day of the month (used for as-of joins). |
| `day_of_week` | integer | 1 = Sunday … 7 = Saturday (`extract(dow) + 1`). |
| `day_name` | text | Weekday name. |
| `week_of_year`, `month`, `month_name`, `quarter`, `year` | int/text | Calendar parts. |
| `is_weekend` | boolean | True for Sat/Sun. |
| `season` | text | `Winter` (Dec–Feb), `Spring`, `Summer`, `Autumn`. |

### gold.dim_bidding_zone / gold.dim_station  *(reference dims)*
Zone: `zone_key`, `zone_id` (SE1–SE4), `zone_name`, `region`, example counties/municipalities/grid
hubs, `contains_stockholm`, `notes`. Station: SMHI station identity, `data_source`,
`parameter_code`, `zone_id`, `first_ts`/`last_ts` coverage.

### gold.fact_daily  *(the core daily fact — price, bill, weather, hydro)*
One row per (date, zone). Joins spot price, weather, forecast, hydro and the consumer price
tax/fee.

| column | type | meaning & value |
|---|---|---|
| `date_key`, `zone_key` | int | Dimension keys (`dim_calendar`, `dim_bidding_zone`). |
| `date_local`, `effective_month`, `zone_id` | | The date / month / zone. |
| `price_eur_mwh_avg/min/max` | numeric | Daily min/avg/max of the hourly day-ahead price (EUR/MWh). |
| `price_sek_kwh_avg/min/max` | numeric | Same in **SEK/kWh** (from `entsoe_timeseries.price_sek_kwh`). |
| `price_peak_avg_sek_kwh` | numeric | Avg price in **peak hours 06:00–22:00** (local). |
| `price_offpeak_avg_sek_kwh` | numeric | Avg price in **off-peak hours 22:00–06:00** (local). |
| `cheapest_hour_local` | integer | The hour (0–23) with the lowest price that day. |
| `eur_sek_rate` | numeric | EUR→SEK rate used that day. |
| `energy_tax_sek_kwh` | numeric | Energy tax (elskatt) from `consumer_prices` (`hushall`/`DA`), **as-of carried forward**. |
| `grid_fee_sek_kwh` | numeric | Grid fee (elnatspris) from `consumer_prices` (`elnat`/`1`/`viktat`), **as-of carried forward**. |
| `vat_rate` | numeric | Constant `0.25` (25 % VAT). |
| `total_consumer_sek_kwh` | numeric | **The bill:** `(price_sek_kwh_avg + energy_tax + grid_fee) × 1.25`. |
| `temp_c_avg/min/max`, `wind_speed_ms_avg`, `precipitation_mm_sum` | numeric | Observed weather that day (from `weather_observations_hourly`). |
| `forecast_reference_time`, `forecast_temp_c_avg`, `forecast_wind_ms_avg`, `forecast_precipitation_mm_sum` | | The weather forecast for that day (from `weather_forecast_hourly`). |
| `temp_forecast_error_c` | numeric | **`temp_c_avg − forecast_temp_c_avg`** (observed minus forecast). |
| `discharge_m3s` | numeric | Avg hydro discharge (m³/s) that day. |
| `obs_year` | integer | Year. |

### gold.gas_price_daily_sek  *(gas converted to SEK)*

| column | type | meaning & value |
|---|---|---|
| `gas_date`, `date_key`, `effective_month`, `obs_year` | | Date dimension parts. |
| `gas_price_usd_mmbtu` | numeric | US$/MMBtu from EIA. |
| `sek_per_eur`, `usd_per_eur` | numeric | ECB rates (as-of carried forward). |
| `usd_sek_rate` | numeric | `sek_per_eur / usd_per_eur` (USD→SEK cross rate). |
| `gas_price_sek_mmbtu` | numeric | `gas_price_usd_mmbtu × usd_sek_rate`. |
| `gas_price_sek_kwh` | numeric | **`gas_price_sek_mmbtu / 293.071`** (MMBtu → kWh). |

### gold.driver_daily  *(long-format drivers for the "what moves the price" analysis)*
Un-pivots the drivers so each row is one (date, zone, driver).

| column | type | meaning & value |
|---|---|---|
| `date_local`, `zone_id` | | The date / zone. |
| `spot_sek_kwh` | numeric | The day's spot price (`price_sek_kwh_avg`). |
| `driver_name` | text | `Temp Avg °C`, `Wind Avg m/s`, `Precipitation mm`, `Discharge m3/s`, `Gas Price SEK/MMBtu`. |
| `driver_value` | numeric | That driver's value that day (from `fact_daily` / `gas_price_daily_sek`). |

### gold.thermostat_dataset_stockholm  *(flattened feature table for heating/thermostat work)*
`fact_daily` + `dim_calendar` + `dim_bidding_zone`, filtered to **SE3 + SE4**. Columns are the
calendar, zone, price, bill, weather, forecast and hydro fields described above — it is a
modeling-ready flat table, not a thermostat log.

---

## 5. ML layer — `gold.price_forecast*` (from `ml/price_forecast.ipynb`)

A gradient-boosted model forecasts the next-day spot price per zone; quantile regression gives a
p10–p90 range. Bill = `(spot + tax + fee) × 1.25`. Written by the notebook, not dbt.

### gold.price_forecast  *(daily forecast + backtest, per zone)*

| column | type | meaning & value |
|---|---|---|
| `zone` | text | SE1–SE4. |
| `target_date` | date | The day being predicted. |
| `lead_days` | integer | Days ahead of the generation date. |
| `lead_bucket` | text | `1`, `2-8`, `9-62` (forecast lead group). |
| `generated_at` | timestamp | When the forecast was produced. |
| `is_forecast` | boolean | `true` = future forecast, `false` = back-test (with actual). |
| `spot_sek_kwh` | numeric | Predicted spot price (p50 / central), SEK/kWh. |
| `spot_p10_sek_kwh`, `spot_p90_sek_kwh` | numeric | 10th/90th percentile of the spot forecast (the band). |
| `actual_sek_kwh` | numeric | The realised spot price (filled on back-test rows). |
| `energy_tax_sek_kwh`, `grid_fee_sek_kwh` | numeric | Tax and grid fee applied to build the bill. |
| `total_bill_sek_kwh` | numeric | **`(spot + tax + fee) × 1.25`** — the all-in bill forecast. |
| `total_bill_p10_sek_kwh`, `total_bill_p90_sek_kwh` | numeric | Bill range (p10/p90 of the bill). |
| `obs_year` | integer | Year. |

### gold.price_forecast_summary  *(aggregated to horizons)*
Same measures rolled up to `horizon` = `next-day` / `next-week` / `next-month`, with
`period_start`, `period_end`, `model_used`. Used for the "next day/week/month" cards and the
bill estimator.

### gold.price_model_evidence  *(model diagnostics)*

| column | type | meaning & value |
|---|---|---|
| `analysis` | text | `backtest`, `correlation`, `importance`, `ablation`. |
| `name` | text | Feature/model name (e.g. `temp_now`, `gas_asof`). |
| `zone`, `horizon_bucket` | text | Scope of the metric. |
| `metric_name` | text | e.g. `mae_ore_kwh`, `hit_rate`, `pearson_r_deseasoned`, `gbt_importance`, `mae_delta_ore`. |
| `metric_value` | numeric | The value. |
| `n` | bigint | Sample size behind the metric. |
| `run_at` | timestamp | When the evidence was recorded. |
