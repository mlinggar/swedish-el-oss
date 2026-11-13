# bronze layer — raw payload parsed to typed columns

Bronze takes each `raw.*.payload` and extracts it into typed columns. Nothing is de-duplicated or
converted here — that happens in silver. Every bronze table adds the ingest envelope:

| column | type | meaning |
|---|---|---|
| `source_file` | text | The raw file the row was parsed from. |
| `load_tier` | text | `historical` / `daily`. |
| `file_modification_time` | timestamptz | Source timestamp (used downstream to keep the newest). |
| `extracted_at` | timestamptz | When the row was parsed. |

## Tables

### bronze.entsoe_points
One row per ENTSO-E data point (price / load / generation).

| column | type | meaning & value |
|---|---|---|
| `data_item_code` | text | ENTSO-E item (`ENERGY_PRICES`, `DAY_AHEAD_TOTAL_LOAD_FORECAST_R3`, …). Mapped to `metric` in silver. |
| `business_dim` | jsonb | Business dimensions from the XML (e.g. `PRODUCTION_TYPE`, `CONTRACT_TYPE`). |
| `instance_attr` | jsonb | Instance attributes (e.g. `BIDDING_ZONE`). |
| `period_from`, `period_to` | text | The time period the series covers. |
| `resolution` | text | Point resolution, e.g. `PT60M` (hourly). |
| `point_index` | integer | 1-based position within the period. |
| `point_ts_utc` | timestamptz | Point timestamp (UTC) = period start + (index − 1) × resolution. |
| `value_1`, `value_2` | text | Numeric values as text (price, or generation / secondary value). |

### bronze.scb_price_measures
One row per SCB consumer-price observation.

| column | type | meaning & value |
|---|---|---|
| `table_name` | text | SCB source table (`hushall`, `elnat`, …). |
| `dims` | jsonb | Dimensions (`Kundkategori`, `Avtalstyp`, `Elomrade`, `Viktat`, …). |
| `period` | jsonb | The price period (e.g. `2024H1`, `2024M01`). |
| `measure_code` | text | SCB measure code (e.g. `000006WO`). Mapped to `measure_key` in silver. |
| `measure_text`, `measure_value` | text / jsonb | Human label and the value (öre/kWh). |

### bronze.ecb_fx_rates
| column | type | meaning |
|---|---|---|
| `obs_date` | date | Rate date. |
| `currency`, `currency_denom`, `exr_type` | text | Currency pair and rate type (e.g. SEK per EUR). |
| `rate` | text | The rate, as text (typed downstream). |
| `series_key`, `obs_index` | text/int | ECB series identity and period index. |

### bronze.eia_gas_prices
| column | type | meaning |
|---|---|---|
| `obs_date` | date | Price date. |
| `gas_price`, `units` | text | Price and unit (US$/MMBtu) as text. |
| `series`, `series_description`, `area_name`, `product_name`, `process_name` | text | EIA series metadata. |
| `data_map` | jsonb | The rest of the EIA record. |

### bronze.smhi_forecast_points
| column | type | meaning |
|---|---|---|
| `zone` | text | Bidding zone. |
| `reference_time` | timestamptz | When the forecast was issued. |
| `forecast_ts`, `interval_parameters_start` | timestamptz | Valid time of the forecast / interval start. |
| `lat`, `lon` | double | Grid point coordinates. |
| `data_map` | jsonb | The forecast parameters (temperature, wind, …). |

### bronze.smhi_hydro_observations / smhi_metobs_observations
| column | type | meaning |
|---|---|---|
| `zone`, `station_id`, `station_name`, `station_owner` | text | Station identity. |
| `parameter_code`, `parameter_key`, `parameter_name`, `unit` | text | Observed parameter. |
| `period_key` | text | Aggregation period. |
| `obs_ts` | timestamptz | Observation time. |
| `value`, `quality` | text | Value and quality flag, as text. |
| `updated_epoch_ms` | bigint | Source update time. |
| `source_format` | text | `json` or `csv` (metobs has two paths). |

## Downstream
`silver/` de-duplicates (on `file_modification_time`), types the values and converts units
(see `dbt/models/silver/README.md`).
