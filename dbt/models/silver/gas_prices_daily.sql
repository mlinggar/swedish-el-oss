{{ config(materialized='table', schema='silver') }}
with deduped as (
    select * from (
        select g.*,
               row_number() over (
                   partition by obs_date, series
                   order by file_modification_time desc) as rn
        from {{ ref('eia_gas_prices') }} g
    ) t where rn = 1
)
select
    obs_date                    as gas_date,
    nullif(trim(gas_price), '')::numeric as gas_price_usd_mmbtu,
    series, units, source_file, load_tier,
    now() as silver_generated_at
from deduped
