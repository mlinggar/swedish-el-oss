{{ config(materialized='table', schema='gold') }}

-- Hourly thermostat dataset (SE3/SE4): one row per hour x zone.
--   is_forecast=false -> actual past hours (silver actuals)
--   is_forecast=true  -> predicted future hours (ML daily spot spread by the intraday
--                        price shape, temp from the SMHI hourly forecast)
-- Bill = (spot + tax + fee) * 1.25.  Heating cost = (max(0, 15 - temp) / COP) * bill.
-- shortcut: base temp 15C and heat-pump COP 3 are illustrative constants; tune per home.
-- shortcut: hourly forecast = ML daily price x mean intraday shape (assumes the future
--            day's intraday pattern matches the 90-day average).

with shape as (
    -- intraday price shape (last 90 days): hour-of-day avg price / overall avg price
    select h.bidding_zone as zone, h.hour_of_day, h.havg / o.oavg as shape_ratio
    from (
        select bidding_zone, extract(hour from ts_local)::int as hour_of_day, avg(price_sek_kwh) as havg
        from {{ ref('entsoe_timeseries') }}
        where metric = 'day_ahead_price' and price_sek_kwh is not null
          and ts_local >= now() - interval '90 days'
        group by 1, 2
    ) h
    join (
        select bidding_zone, avg(price_sek_kwh) as oavg
        from {{ ref('entsoe_timeseries') }}
        where metric = 'day_ahead_price' and price_sek_kwh is not null
          and ts_local >= now() - interval '90 days'
        group by 1
    ) o on o.bidding_zone = h.bidding_zone
),
hist_spot as (
    -- past hours, one row per hour x zone (aggregate away PT15M/PT60M mix)
    select date_trunc('hour', ts_local) as ts_local, bidding_zone as zone, avg(price_sek_kwh) as spot_sek_kwh
    from {{ ref('entsoe_timeseries') }}
    where metric = 'day_ahead_price' and price_sek_kwh is not null
      and bidding_zone in ('SE3', 'SE4')
      and ts_local < date_trunc('hour', now())
    group by 1, 2
),
hist_temp as (
    select date_trunc('hour', ts_local) as ts_local, zone, avg(value) as temp_c
    from {{ ref('weather_observations_hourly') }}
    where parameter_code = 'temp'
    group by 1, 2
),
historical as (
    select
        hs.ts_local, hs.zone, hs.spot_sek_kwh, ht.temp_c,
        false as is_forecast,
        null::numeric as spot_p10_sek_kwh, null::numeric as spot_p90_sek_kwh
    from hist_spot hs
    left join hist_temp ht on ht.zone = hs.zone and ht.ts_local = hs.ts_local
),
fc as (
    -- future hours + predicted temp (latest reference_time per hour x zone)
    select distinct on (zone, date_trunc('hour', ts_local))
        date_trunc('hour', ts_local) as ts_local, zone, air_temperature as temp_c
    from {{ ref('weather_forecast_hourly') }}
    where zone in ('SE3', 'SE4') and ts_local >= date_trunc('hour', now())
    order by zone, date_trunc('hour', ts_local), reference_time desc
),
fc_daily as (
    -- freshest ML daily predicted spot per zone x target_date
    select distinct on (zone, target_date)
        zone, target_date,
        spot_sek_kwh as daily_spot,
        spot_p10_sek_kwh as daily_spot_p10,
        spot_p90_sek_kwh as daily_spot_p90
    from {{ source('ml', 'price_forecast') }}
    where zone in ('SE3', 'SE4')
    order by zone, target_date, lead_days asc
),
forecast as (
    select
        f.ts_local, f.zone,
        (d.daily_spot * sh.shape_ratio) as spot_sek_kwh,
        f.temp_c,
        true as is_forecast,
        (d.daily_spot_p10 * sh.shape_ratio) as spot_p10_sek_kwh,
        (d.daily_spot_p90 * sh.shape_ratio) as spot_p90_sek_kwh
    from fc f
    left join fc_daily d on d.zone = f.zone and d.target_date = f.ts_local::date
    left join shape sh on sh.zone = f.zone and sh.hour_of_day = extract(hour from f.ts_local)::int
),
combined as (
    select * from historical
    union all
    select * from forecast
),
tax_fee as (
    -- tax/fee are constant within a month (as-of carried); resolve once per month, not per row
    select
        m.effective_month,
        tax.energy_tax_sek_kwh,
        fee.grid_fee_sek_kwh
    from (select distinct date_trunc('month', ts_local)::date as effective_month from combined) m
    left join lateral (
        select cp.elskatt_sek_kwh as energy_tax_sek_kwh
        from {{ ref('consumer_prices') }} cp
        where cp.table_name = 'hushall' and cp.customer_category = 'DA'
          and cp.period_start <= m.effective_month
        order by cp.period_start desc limit 1
    ) tax on true
    left join lateral (
        select cp.elnatspris_sek_kwh as grid_fee_sek_kwh
        from {{ ref('consumer_prices') }} cp
        where cp.table_name = 'elnat' and cp.customer_category = '1' and cp.weighting = 'viktat'
          and cp.period_start <= m.effective_month
        order by cp.period_start desc limit 1
    ) fee on true
),
enriched as (
    select
        c.ts_local, c.zone, c.spot_sek_kwh, c.temp_c, c.is_forecast,
        c.spot_p10_sek_kwh, c.spot_p90_sek_kwh,
        tf.energy_tax_sek_kwh,
        tf.grid_fee_sek_kwh,
        (c.spot_sek_kwh    + coalesce(tf.energy_tax_sek_kwh, 0) + coalesce(tf.grid_fee_sek_kwh, 0)) * 1.25 as bill_sek_kwh,
        (c.spot_p10_sek_kwh + coalesce(tf.energy_tax_sek_kwh, 0) + coalesce(tf.grid_fee_sek_kwh, 0)) * 1.25 as bill_p10_sek_kwh,
        (c.spot_p90_sek_kwh + coalesce(tf.energy_tax_sek_kwh, 0) + coalesce(tf.grid_fee_sek_kwh, 0)) * 1.25 as bill_p90_sek_kwh,
        case when c.temp_c is null then null else greatest(0, 15 - c.temp_c) end as heating_demand
    from combined c
    join tax_fee tf on tf.effective_month = date_trunc('month', c.ts_local)::date
)
select
    e.ts_local,
    e.ts_local::date as date_local,
    e.zone,
    zb.zone_name,
    zb.region,
    extract(hour from e.ts_local)::int as hour_of_day,
    e.is_forecast,
    now() as generated_at,
    e.spot_sek_kwh,
    e.spot_p10_sek_kwh,
    e.spot_p90_sek_kwh,
    e.energy_tax_sek_kwh,
    e.grid_fee_sek_kwh,
    0.25 as vat_rate,
    e.bill_sek_kwh,
    e.bill_p10_sek_kwh,
    e.bill_p90_sek_kwh,
    e.temp_c,
    e.heating_demand,
    e.heating_demand / 3.0 as heat_energy_kwh,
    (e.heating_demand / 3.0) * e.bill_sek_kwh    as heat_cost_sek,
    (e.heating_demand / 3.0) * e.bill_p10_sek_kwh as heat_cost_p10_sek,
    (e.heating_demand / 3.0) * e.bill_p90_sek_kwh as heat_cost_p90_sek,
    row_number() over (partition by e.ts_local::date, e.zone order by e.spot_sek_kwh) as price_rank_in_day,
    (row_number() over (partition by e.ts_local::date, e.zone order by e.spot_sek_kwh) <= 4) as is_cheapest_4h,
    extract(year from e.ts_local)::int as obs_year
from enriched e
left join {{ ref('dim_bidding_zone') }} zb on zb.zone_id = e.zone
