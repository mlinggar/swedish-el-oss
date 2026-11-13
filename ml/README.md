# ml layer — price forecast

Produced by `ml/price_forecast.ipynb` (not dbt). A gradient-boosted model forecasts the next-day
spot price per zone; quantile regression produces a p10–p90 range. The bill is built the same way
as `fact_daily`: **`(spot + tax + fee) × 1.25`** (25 % VAT).

The outputs are written into the `gold` schema.

## gold.price_forecast  *(daily forecast + back-test, one row per zone × date)*

| column | type | meaning & value |
|---|---|---|
| `zone` | text | SE1–SE4. |
| `target_date` | date | The day being predicted. |
| `lead_days` | integer | Days ahead of the generation date. |
| `lead_bucket` | text | Forecast lead group: `1`, `2-8`, `9-62`. |
| `generated_at` | timestamp | When the forecast was produced. |
| `is_forecast` | boolean | `true` = future forecast; `false` = back-test (has `actual_sek_kwh`). |
| `spot_sek_kwh` | numeric | Predicted spot price (p50 / central), SEK/kWh. |
| `spot_p10_sek_kwh`, `spot_p90_sek_kwh` | numeric | 10th / 90th percentile of the spot forecast (the uncertainty band). |
| `actual_sek_kwh` | numeric | The realised spot price (filled on back-test rows). |
| `energy_tax_sek_kwh`, `grid_fee_sek_kwh` | numeric | Tax and grid fee applied to build the bill. |
| `total_bill_sek_kwh` | numeric | **`(spot + tax + fee) × 1.25`** — the all-in bill forecast. |
| `total_bill_p10_sek_kwh`, `total_bill_p90_sek_kwh` | numeric | Bill range (p10 / p90 of the bill). |
| `obs_year` | integer | Year. |

## gold.price_forecast_summary  *(aggregated to horizons)*
The same measures rolled up to `horizon` = `next-day` / `next-week` / `next-month`, with
`period_start`, `period_end` and `model_used`. Feeds the "next day / week / month" cards and the
bill estimator on the site.

## gold.price_model_evidence  *(model diagnostics)*

| column | type | meaning & value |
|---|---|---|
| `analysis` | text | `backtest`, `correlation`, `importance`, `ablation`. |
| `name` | text | Feature / model name (e.g. `temp_now`, `gas_asof`). |
| `zone`, `horizon_bucket` | text | Scope of the metric. |
| `metric_name` | text | `mae_ore_kwh`, `hit_rate`, `pearson_r_deseasoned`, `gbt_importance`, `mae_delta_ore`. |
| `metric_value` | numeric | The value. |
| `n` | bigint | Sample size behind the metric. |
| `run_at` | timestamp | When the evidence was recorded. |
