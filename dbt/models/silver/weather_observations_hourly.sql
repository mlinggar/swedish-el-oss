{{ config(materialized='incremental', incremental_strategy='delete+insert',
          unique_key='_key', schema='silver') }}
with src as (
    select m.*,
           md5(coalesce(station_id, '~') || '|' || coalesce(parameter_code, '~') || '|'
               || coalesce(obs_ts::text, '~')) as _key,
           case when source_format = 'archive_csv' then 0 else 1 end as _prio,
           file_modification_time as _fmod
    from {{ ref('smhi_metobs_observations') }} m
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
    zone, station_id, station_name, parameter_code, parameter_name, unit,
    obs_ts                                        as ts_utc,
    obs_ts at time zone 'Europe/Stockholm'         as ts_local,
    nullif(trim(value), '')::numeric               as value,
    quality, source_format, source_file, load_tier,
    extract(year from obs_ts)::int                 as obs_year,
    now() as silver_generated_at,
    _key, _prio, _fmod
from deduped
