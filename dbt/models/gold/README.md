# gold layer — business tables

Gold builds the analysis-ready tables: dimensions, the daily fact (price + bill + weather + hydro),
the gas price in SEK, the driver table and the thermostat feature table.

**The bill (what the consumer pays):**
`total_consumer_sek_kwh = (price_sek_kwh_avg + energy_tax_sek_kwh + grid_fee_sek_kwh) × 1.25`
— the 1.25 is 25 % VAT (`vat_rate`). Energy tax and grid fee are pulled from `consumer_prices` and
**as-of carried forward** to each month.

## Tables

### gold.dim_calendar  *(date dimension, 2022–2030, one row per day)*
| column | type | meaning & value |
|---|---|---|
| `date_key` | integer | `YYYYMMDD` surrogate key. |
| `date_local` | date | The date. |
| `effective_month` | date | First day of the month (used for as-of joins). |
| `day_of_week` | integer | 1 = Sunday … 7 = Saturday (`extract(dow) + 1`). |
| `day_name` | text | Weekday name. |
| `week_of_year`, `month`, `month_name`, `quarter`, `year` | int/text | Calendar parts. |
| `is_weekend` | boolean | True for Saturday/Sunday. |
| `season` | text | `Winter` (Dec–Feb), `Spring` (Mar–May), `Summer` (Jun–Aug), `Autumn` (Sep–Nov). |

### gold.dim_bidding_zone  *(reference)*
`zone_key`, `zone_id` (SE1–SE4), `zone_name`, `region`, `counties_example`,
`municipalities_example`, `grid_hubs_example`, `contains_stockholm`, `notes`.

### gold.dim_station  *(reference)*
`station_key`, `station_id`, `station_name`, `station_owner`, `data_source`, `parameter_code`,
`zone_id`, `first_ts`, `last_ts` (coverage).

### gold.fact_daily  *(the core daily fact — one row per date × zone)*
Joins spot price, weather, forecast, hydro and the consumer tax/fee.

| column | type | meaning & value |
|---|---|---|
| `date_key`, `zone_key` | int | Dimension keys (`dim_calendar`, `dim_bidding_zone`). |
| `date_local`, `effective_month`, `zone_id` | | Date / month / zone. |
| `price_eur_mwh_avg/min/max` | numeric | Daily min/avg/max hourly day-ahead price (EUR/MWh). |
| `price_sek_kwh_avg/min/max` | numeric | Same in **SEK/kWh** (from `entsoe_timeseries.price_sek_kwh`). |
| `price_peak_avg_sek_kwh` | numeric | Avg price in **peak hours 06:00–22:00** local. |
| `price_offpeak_avg_sek_kwh` | numeric | Avg price in **off-peak hours 22:00–06:00** local. |
| `cheapest_hour_local` | integer | The hour (0–23) with the lowest price that day. |
| `eur_sek_rate` | numeric | EUR→SEK rate used that day. |
| `energy_tax_sek_kwh` | numeric | Energy tax (elskatt, `hushall`/`DA`), as-of carried forward. |
| `grid_fee_sek_kwh` | numeric | Grid fee (elnatspris, `elnat`/`1`/`viktat`), as-of carried forward. |
| `vat_rate` | numeric | Constant `0.25`. |
| `total_consumer_sek_kwh` | numeric | **The bill: `(spot + tax + fee) × 1.25`**. |
| `temp_c_avg/min/max`, `wind_speed_ms_avg`, `precipitation_mm_sum` | numeric | Observed weather that day. |
| `forecast_reference_time`, `forecast_temp_c_avg`, `forecast_wind_ms_avg`, `forecast_precipitation_mm_sum` | | Weather forecast for that day. |
| `temp_forecast_error_c` | numeric | **`temp_c_avg − forecast_temp_c_avg`** (observed minus forecast). |
| `discharge_m3s` | numeric | Avg hydro discharge (m³/s) that day. |
| `obs_year` | integer | Year. |

### gold.gas_price_daily_sek  *(gas → SEK)*
| column | type | meaning & value |
|---|---|---|
| `gas_date`, `date_key`, `effective_month`, `obs_year` | | Date parts. |
| `gas_price_usd_mmbtu` | numeric | US$/MMBtu (EIA). |
| `sek_per_eur`, `usd_per_eur` | numeric | ECB rates (as-of carried forward). |
| `usd_sek_rate` | numeric | `sek_per_eur / usd_per_eur` (USD→SEK cross rate). |
| `gas_price_sek_mmbtu` | numeric | `gas_price_usd_mmbtu × usd_sek_rate`. |
| `gas_price_sek_kwh` | numeric | **`gas_price_sek_mmbtu / 293.071`** (MMBtu → kWh). |

### gold.driver_daily  *(long-format drivers — for the "what moves the price" analysis)*
Un-pivots the drivers so each row is one (date, zone, driver).

| column | type | meaning & value |
|---|---|---|
| `date_local`, `zone_id` | | Date / zone. |
| `spot_sek_kwh` | numeric | The day's spot price (`price_sek_kwh_avg`). |
| `driver_name` | text | `Temp Avg °C`, `Wind Avg m/s`, `Precipitation mm`, `Discharge m3/s`, `Gas Price SEK/MMBtu`. |
| `driver_value` | numeric | That driver's value that day (from `fact_daily` / `gas_price_daily_sek`). |

### gold.thermostat_dataset_stockholm  *(flat feature table for heating/thermostat work)*
`fact_daily` + `dim_calendar` + `dim_bidding_zone`, filtered to **SE3 + SE4**. It carries the
calendar, zone, price, bill, weather, forecast and hydro fields above — a modeling-ready flat
table (not a thermostat log).

## Downstream
`ml/` forecasts the spot price from these features (see `ml/README.md`); `site/` serves them.
