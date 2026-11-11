-- swedish-el-oss: warehouse bootstrap (idempotent, safe to re-run)
-- raw = ingest-owned. bronze/silver/gold = dbt-owned.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- raw payload tables (identical shape): idempotency key (input_file_name, file_modification_time)
CREATE TABLE IF NOT EXISTS raw.raw_entsoe (
  input_file_name text NOT NULL, file_modification_time timestamptz NOT NULL,
  load_tier text NOT NULL, payload jsonb NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time));

CREATE TABLE IF NOT EXISTS raw.raw_eia (
  input_file_name text NOT NULL, file_modification_time timestamptz NOT NULL,
  load_tier text NOT NULL, payload jsonb NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time));

CREATE TABLE IF NOT EXISTS raw.raw_ecb (
  input_file_name text NOT NULL, file_modification_time timestamptz NOT NULL,
  load_tier text NOT NULL, payload jsonb NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time));

CREATE TABLE IF NOT EXISTS raw.raw_scb (
  input_file_name text NOT NULL, file_modification_time timestamptz NOT NULL,
  load_tier text NOT NULL, payload jsonb NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time));

CREATE TABLE IF NOT EXISTS raw.raw_smhi_metobs (
  input_file_name text NOT NULL, file_modification_time timestamptz NOT NULL,
  load_tier text NOT NULL, payload jsonb NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time));

CREATE TABLE IF NOT EXISTS raw.raw_smhi_forecast (
  input_file_name text NOT NULL, file_modification_time timestamptz NOT NULL,
  load_tier text NOT NULL, payload jsonb NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time));

CREATE TABLE IF NOT EXISTS raw.raw_smhi_hydro (
  input_file_name text NOT NULL, file_modification_time timestamptz NOT NULL,
  load_tier text NOT NULL, payload jsonb NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (input_file_name, file_modification_time));

-- archive CSV pre-parsed at ingest into relational rows (fast; no jsonb unnest downstream)
CREATE TABLE IF NOT EXISTS raw.smhi_metobs_archive_rows (
  source_file text, file_modification_time timestamptz, load_tier text,
  zone text, parameter_code text, station_id text, station_name text,
  parameter_name text, unit text,
  obs_date text, obs_time text, value text, quality text);

GRANT USAGE ON SCHEMA raw, bronze, silver, gold TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO PUBLIC;
