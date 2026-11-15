{{ config(materialized='incremental', incremental_strategy='delete+insert',
          unique_key='_key', schema='silver') }}
with src as (
    select f.*,
           md5(coalesce(zone, '~') || '|' || coalesce(reference_time::text, '~') || '|'
               || coalesce(forecast_ts::text, '~')) as _key,
           0 as _prio,
           file_modification_time as _fmod
    from {{ ref('smhi_forecast_points') }} f
),
new_rows as (
    select * from src s
    {% if is_incremental() %}
    where s._fmod > (select coalesce(max(_fmod), '-infinity')::timestamptz from {{ this }})
      and not exists (
          select 1 from {{ this }} t
          where t._key = s._key
            and (t._prio < s._prio or (t._prio = s._prio and t._fmod > s._fmod)))
    {% endif %}
),
deduped as (
    select * from (
        select s.*,
               row_number() over (partition by s._key order by s._prio asc, s._fmod desc) as rn
        from new_rows s
    ) x where rn = 1
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
    now() as silver_generated_at,
    _key, _prio, _fmod
from deduped
