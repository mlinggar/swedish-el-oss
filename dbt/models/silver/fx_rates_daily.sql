{{ config(materialized='incremental', incremental_strategy='delete+insert',
          unique_key='_key', schema='silver') }}
with src as (
    select f.*,
           md5(coalesce(currency, '~') || '|' || coalesce(obs_date::text, '~')) as _key,
           0 as _prio,
           file_modification_time as _fmod
    from {{ ref('ecb_fx_rates') }} f
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
    obs_date, currency, currency_denom, exr_type,
    nullif(trim(rate), '')::numeric as rate,
    series_key, source_file, load_tier,
    now() as silver_generated_at,
    _key, _prio, _fmod
from deduped
