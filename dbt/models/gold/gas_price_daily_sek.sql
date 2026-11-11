{{ config(materialized='table', schema='gold') }}
select
    g.gas_date,
    to_char(g.gas_date, 'YYYYMMDD')::int        as date_key,
    date_trunc('month', g.gas_date)::date       as effective_month,
    g.gas_price_usd_mmbtu,
    sek.sek_per_eur, usd.usd_per_eur,
    (sek.sek_per_eur / usd.usd_per_eur)         as usd_sek_rate,
    g.gas_price_usd_mmbtu * (sek.sek_per_eur / usd.usd_per_eur) as gas_price_sek_mmbtu,
    (g.gas_price_usd_mmbtu * (sek.sek_per_eur / usd.usd_per_eur)) / 293.071 as gas_price_sek_kwh,
    extract(year from g.gas_date)::int          as obs_year
from {{ ref('gas_prices_daily') }} g
left join lateral (
    select rate as sek_per_eur from {{ ref('fx_rates_daily') }}
    where currency='SEK' and obs_date <= g.gas_date order by obs_date desc limit 1
) sek on true
left join lateral (
    select rate as usd_per_eur from {{ ref('fx_rates_daily') }}
    where currency='USD' and obs_date <= g.gas_date order by obs_date desc limit 1
) usd on true
