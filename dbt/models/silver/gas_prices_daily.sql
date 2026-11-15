{{ config(materialized='incremental', incremental_strategy='delete+insert',
          unique_key='_key', schema='silver') }}
with src as (
    select g.*,
           md5(coalesce(obs_date::text, '~') || '|' || coalesce(series, '~')) as _key,
           0 as _prio,
           file_modification_time as _fmod
    from {{ ref('eia_gas_prices') }} g
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
    obs_date                    as gas_date,
    nullif(trim(gas_price), '')::numeric as gas_price_usd_mmbtu,
    series, units, source_file, load_tier,
    now() as silver_generated_at,
    _key, _prio, _fmod
from deduped
