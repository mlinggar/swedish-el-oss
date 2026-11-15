{{ config(materialized='incremental', incremental_strategy='delete+insert',
          unique_key='_key', schema='silver') }}
with src as (
    select e.*,
           md5(coalesce(substring(source_file from '/(SE[1-4])/'), '~') || '|'
               || coalesce(data_item_code, '~') || '|'
               || coalesce(business_dim->>'PRODUCTION_TYPE', '~') || '|'
               || coalesce(point_ts_utc::text, '~') || '|'
               || coalesce(resolution, '~')) as _key,
           0 as _prio,
           file_modification_time as _fmod
    from {{ ref('entsoe_points') }} e
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
),
base as (
    select
        substring(source_file from '/(SE[1-4])/')       as bidding_zone,
        case data_item_code
            when 'ENERGY_PRICES' then 'day_ahead_price'
            when 'DAY_AHEAD_TOTAL_LOAD_FORECAST_R3' then 'load_forecast'
            when 'ACTUAL_TOTAL_LOAD_R3' then 'actual_load'
            when 'AGGREGATED_GENERATION_PER_TYPE_R3' then 'actual_generation'
        end                                             as metric,
        business_dim->>'PRODUCTION_TYPE'                as production_type,
        business_dim->>'CONTRACT_TYPE'                  as contract_type,
        resolution,
        point_ts_utc                                    as ts_utc,
        point_ts_utc at time zone 'Europe/Stockholm'     as ts_local,
        nullif(trim(value_1), '')::numeric               as value,
        nullif(trim(value_2), '')::numeric               as value_secondary,
        source_file, load_tier,
        extract(year from point_ts_utc)::int            as obs_year,
        _key, _prio, _fmod
    from deduped
),
fx as (
    select obs_date as fx_date, nullif(trim(rate), '')::numeric as eur_sek
    from (select * from (
            select f.*, row_number() over (
                partition by currency, obs_date order by file_modification_time desc) as rn
            from {{ ref('ecb_fx_rates') }} f) x where rn = 1) t
    where currency = 'SEK'
),
fx_first as (select eur_sek from fx order by fx_date asc limit 1)
select
    b.*,
    case when b.metric = 'day_ahead_price' then f.eur_sek end       as eur_sek_rate,
    case when b.metric = 'day_ahead_price'
         then b.value / 1000.0 * coalesce(f.eur_sek, (select eur_sek from fx_first))
    end                                                             as price_sek_kwh
from base b
left join lateral (
    select eur_sek from fx where fx.fx_date <= b.ts_utc::date order by fx.fx_date desc limit 1
) f on true
