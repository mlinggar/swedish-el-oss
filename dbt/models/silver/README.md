# silver layer — cleaned, conformed, derived

Silver de-duplicates bronze (keeping the newest `file_modification_time`), types the values and
applies the unit / currency conversions. This is where prices become SEK/kWh.

## Conventions
- **`price_sek_kwh = value (EUR/MWh) / 1000.0 × eur_sek_rate`** — MWh→kWh, EUR→SEK.
- **`*_sek_kwh = *_ore_kwh / 100.0`** — SCB prices arrive in öre/kWh.
- `ts_local` = `ts_utc at time zone 'Europe/Stockholm'`.

## Tables

### silver.entsoe_timeseries  *(hourly spot price / load / generation)*
| column | type | meaning & value |
|---|---|---|
| `bidding_zone` | text | SE1–SE4 (parsed from the source path). |
| `metric` | text | `day_ahead_price`, `load_forecast`, `actual_load`, `actual_generation` (from `data_item_code`). |
| `production_type`, `contract_type` | text | From `business_dim`. |
| `resolution` | text | e.g. `PT60M`. |
| `ts_utc`, `ts_local` | timestamptz / timestamp | Point time (UTC and Stockholm). |
| `value` | numeric | Raw value (EUR/MWh for prices; MW for load/generation). |
| `value_secondary` | numeric | Secondary value where the source has one. |
| `eur_sek_rate` | numeric | ECB EUR→SEK rate as-of `ts_utc` (fallback = earliest known rate). |
| `price_sek_kwh` | numeric | **`value / 1000.0 × eur_sek_rate`** (only for `day_ahead_price`). |
| `obs_year` | integer | Year of `ts_utc`. |

### silver.consumer_prices  *(SCB consumer prices, pivoted)*
One row per (table, category, period) with each price measure pivoted to a column.
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
| `*_ore_kwh` | numeric | Price in **öre/kWh** per measure (handelspris, natpris, elskatt, elhandelspris, elnatspris, …). |
| `*_sek_kwh` | numeric | Same price in **SEK/kWh** = `*_ore_kwh / 100.0`. |
| `silver_generated_at` | timestamptz | Build timestamp. |

### silver.fx_rates_daily  *(ECB FX)*
`obs_date`, `currency` (e.g. `SEK`), `currency_denom`, `exr_type`, `rate` (currency per EUR),
`series_key`. Drives all EUR→SEK and USD→SEK conversion.

### silver.gas_prices_daily  *(EIA gas)*
`gas_date`, `gas_price_usd_mmbtu` (US$/MMBtu), `series`, `units`. Converted to SEK/kWh in gold.

### silver.weather_observations_hourly  *(SMHI observations)*
`zone`, `station_id`/`station_name`, `parameter_code`/`parameter_name`/`unit`, `ts_utc`/`ts_local`,
`value`, `quality`, `source_format`.

### silver.weather_forecast_hourly  *(SMHI forecast)*
`zone`, `reference_time`, `ts_utc`/`ts_local`, `air_temperature`, `wind_speed`, `wind_speed_of_gust`,
`precipitation_amount_mean`, `relative_humidity`, `cloud_area_fraction`, `lat`, `lon`.

### silver.smhi_hydro_observations_daily  *(SMHI hydro)*
`zone`, `station_*`, `parameter_code` (discharge), `value` (m³/s), `quality`, `ts_utc`/`ts_local`.

## Downstream
`gold/` builds dimensions, the daily fact and drivers from these (see `dbt/models/gold/README.md`).
