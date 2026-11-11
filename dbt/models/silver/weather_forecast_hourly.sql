{{ config(materialized='table', schema='silver') }}
with deduped as (
    select * from (
        select f.*,
               row_number() over (
                   partition by zone, reference_time, forecast_ts
                   order by file_modification_time desc) as rn
        from {{ ref('smhi_forecast_points') }} f
    ) t where rn = 1
)
select
    zone, reference_time,
    forecast_ts                                   as ts_utc,
    forecast_ts at time zone 'Europe/Stockholm'    as ts_local,
    nullif(trim(data_map->>'air_temperature'), '')::numeric          as air_temperature,
    nullif(trim(data_map->>'wind_speed'), '')::numeric               as wind_speed,
    nullif(trim(data_map->>'wind_speed_of_gust'), '')::numeric       as wind_speed_of_gust,
    nullif(trim(data_map->>'precipitation_amount_mean'), '')::numeric as precipitation_amount_mean,
    nullif(trim(data_map->>'relative_humidity'), '')::numeric        as relative_humidity,
    nullif(trim(data_map->>'cloud_area_fraction'), '')::numeric      as cloud_area_fraction,
    lat, lon, source_file, load_tier,
    extract(year from forecast_ts)::int           as obs_year,
    now() as silver_generated_at
from deduped
