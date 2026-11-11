{{ config(materialized='table', schema='silver') }}
with deduped as (
    select * from (
        select f.*,
               row_number() over (
                   partition by currency, obs_date
                   order by file_modification_time desc) as rn
        from {{ ref('ecb_fx_rates') }} f
    ) t where rn = 1
)
select
    obs_date, currency, currency_denom, exr_type,
    nullif(trim(rate), '')::numeric as rate,
    series_key, source_file, load_tier,
    now() as silver_generated_at
from deduped
