{{ config(materialized='table', schema='silver') }}
with deduped as (
    select * from (
        select m.*,
               row_number() over (
                   partition by station_id, parameter_code, obs_ts
                   order by case when source_format='archive_csv' then 0 else 1 end,
                            file_modification_time desc) as rn
        from {{ ref('smhi_metobs_observations') }} m
    ) t where rn = 1
)
select
    zone, station_id, station_name, parameter_code, parameter_name, unit,
    obs_ts                                        as ts_utc,
    obs_ts at time zone 'Europe/Stockholm'         as ts_local,
    nullif(trim(value), '')::numeric               as value,
    quality, source_format, source_file, load_tier,
    extract(year from obs_ts)::int                 as obs_year,
    now() as silver_generated_at
from deduped
