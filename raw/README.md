# raw layer — verbatim API responses

The `raw` schema holds the unmodified responses from the seven data sources. Nothing is cleaned
here — this is the immutable landing zone. Rows are keyed on (`input_file_name`,
`file_modification_time`), so re-ingesting the same source replaces it instead of duplicating.

The raw tables are created by `warehouse_ddl.sql` and populated by `ingest/` (one module per source).

## Tables

### raw.raw_ecb, raw_eia, raw_entsoe, raw_scb, raw_smhi_forecast, raw_smhi_hydro, raw_smhi_metobs
One row per API response (the source JSON/XML kept as-is).

| column | type | meaning & value |
|---|---|---|
| `input_file_name` | text | Identity of the source request; part of the idempotency key. |
| `file_modification_time` | timestamptz | Source timestamp of the response; part of the idempotency key (newest wins on conflict). |
| `load_tier` | text | Ingest run type: `historical` (backfill) or `daily`. |
| `payload` | jsonb | The raw API response body, stored verbatim (source of truth for bronze). |
| `ingested_at` | timestamptz | When the row was written by the ingest. |

Sources: **ECB** FX rates, **EIA** gas prices, **ENTSO-E** day-ahead prices / load / generation,
**SCB** consumer prices, **SMHI** weather forecast / hydro discharge / weather observations.

### raw.smhi_metobs_archive_rows
The SMHI observation **archive CSV** is parsed into rows here (separate from the JSON dumps).

| column | type | meaning & value |
|---|---|---|
| `source_file` | text | The archive file the row came from. |
| `file_modification_time` | timestamptz | Source timestamp (idempotency key). |
| `load_tier` | text | `historical` / `daily`. |
| `zone` | text | Bidding zone (SE1–SE4). |
| `parameter_code` | text | Observed parameter (`temp`, `wind_speed`, `precipitation`, …). |
| `parameter_name`, `unit` | text | Human-readable parameter and unit. |
| `station_id`, `station_name` | text | SMHI station identity. |
| `obs_date`, `obs_time` | text | Observation timestamp, as text in the source. |
| `value` | text | Observed value, as text (typed downstream). |
| `quality` | text | SMHI quality flag. |

## Downstream
`bronze/` models parse each `payload` into typed columns (see `dbt/models/bronze/README.md`).
