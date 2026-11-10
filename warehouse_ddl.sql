-- swedish-el-oss: warehouse bootstrap (idempotent - safe to re-run)
-- Layer contract: raw = ingest-owned (append-only). bronze/silver/gold = dbt-owned (full refresh).

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- raw layer: one identical shape per source.
-- Idempotency key is (input_file_name, file_modification_time) - the ingest
-- writes with ON CONFLICT DO NOTHING, so re-fetching the same file version is a no-op.
-- payload holds the BOM-stripped JSON (CSV pre-parsed to jsonb rows).

CREATE TABLE IF NOT EXISTS raw.raw_entsoe (
  input_file_name        text        NOT NULL,
  file_modification_time timestamptz NOT NULL,
  load_tier              text        NOT NULL,
  payload                jsonb       NOT NULL,
  ingested_at            timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time)
);

CREATE TABLE IF NOT EXISTS raw.raw_eia (
  input_file_name        text        NOT NULL,
  file_modification_time timestamptz NOT NULL,
  load_tier              text        NOT NULL,
  payload                jsonb       NOT NULL,
  ingested_at            timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time)
);

CREATE TABLE IF NOT EXISTS raw.raw_ecb (
  input_file_name        text        NOT NULL,
  file_modification_time timestamptz NOT NULL,
  load_tier              text        NOT NULL,
  payload                jsonb       NOT NULL,
  ingested_at            timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time)
);

CREATE TABLE IF NOT EXISTS raw.raw_scb (
  input_file_name        text        NOT NULL,
  file_modification_time timestamptz NOT NULL,
  load_tier              text        NOT NULL,
  payload                jsonb       NOT NULL,
  ingested_at            timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time)
);

CREATE TABLE IF NOT EXISTS raw.raw_smhi_metobs (
  input_file_name        text        NOT NULL,
  file_modification_time timestamptz NOT NULL,
  load_tier              text        NOT NULL,
  payload                jsonb       NOT NULL,
  ingested_at            timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time)
);

CREATE TABLE IF NOT EXISTS raw.raw_smhi_forecast (
  input_file_name        text        NOT NULL,
  file_modification_time timestamptz NOT NULL,
  load_tier              text        NOT NULL,
  payload                jsonb       NOT NULL,
  ingested_at            timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time)
);

CREATE TABLE IF NOT EXISTS raw.raw_smhi_hydro (
  input_file_name        text        NOT NULL,
  file_modification_time timestamptz NOT NULL,
  load_tier              text        NOT NULL,
  payload                jsonb       NOT NULL,
  ingested_at            timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time)
);

GRANT USAGE ON SCHEMA raw, bronze, silver, gold TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO PUBLIC;
