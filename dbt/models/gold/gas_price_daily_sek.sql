{{ config(materialized='table', schema='gold') }}
with fx as (
    select currency, obs_date, rate from {{ ref('fx_rates_daily') }}
), earliest as (
    select currency, rate from (
        select currency, rate, row_number() over (partition by currency order by obs_date asc) rn
        from fx) t where rn = 1
)
select
    g.gas_date,
    to_char(g.gas_date, 'YYYYMMDD')::int        as date_key,
    date_trunc('month', g.gas_date)::date       as effective_month,
    g.gas_price_usd_mmbtu,
    coalesce(sek.sek_per_eur, esek.rate)        as sek_per_eur,
    coalesce(usd.usd_per_eur, eusd.rate)        as usd_per_eur,
    (coalesce(sek.sek_per_eur, esek.rate) / coalesce(usd.usd_per_eur, eusd.rate)) as usd_sek_rate,
    g.gas_price_usd_mmbtu * (coalesce(sek.sek_per_eur, esek.rate) / coalesce(usd.usd_per_eur, eusd.rate)) as gas_price_sek_mmbtu,
    (g.gas_price_usd_mmbtu * (coalesce(sek.sek_per_eur, esek.rate) / coalesce(usd.usd_per_eur, eusd.rate))) / 293.071 as gas_price_sek_kwh,
    extract(year from g.gas_date)::int          as obs_year
from {{ ref('gas_prices_daily') }} g
left join lateral (select rate as sek_per_eur from fx where currency='SEK' and obs_date <= g.gas_date order by obs_date desc limit 1) sek on true
left join lateral (select rate as usd_per_eur from fx where currency='USD' and obs_date <= g.gas_date order by obs_date desc limit 1) usd on true
left join earliest esek on esek.currency='SEK'
left join earliest eusd on eusd.currency='USD'
