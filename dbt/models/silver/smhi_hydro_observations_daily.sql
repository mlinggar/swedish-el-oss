{{ config(materialized='table', schema='silver') }}
with deduped as (
    select * from (
        select h.*,
               row_number() over (
                   partition by zone, station_id, obs_ts
                   order by case when source_format='historical_json' then 0 else 1 end,
                            file_modification_time desc) as rn
        from {{ ref('smhi_hydro_observations') }} h
    ) t where rn = 1
)
select
    zone, station_id, station_name, station_owner, parameter_code, parameter_name, unit,
    obs_ts                                        as ts_utc,
    obs_ts at time zone 'Europe/Stockholm'         as ts_local,
    nullif(trim(value), '')::numeric               as value,
    quality, source_format, source_file, load_tier,
    extract(year from obs_ts)::int                 as obs_year,
    now() as silver_generated_at
from deduped
