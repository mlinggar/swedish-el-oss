{{ config(materialized='table', schema='gold') }}
with spot as (
    select
        ts_local::date as date_local, bidding_zone as zone_id,
        avg(value) as price_eur_mwh_avg, min(value) as price_eur_mwh_min, max(value) as price_eur_mwh_max,
        avg(price_sek_kwh) as price_sek_kwh_avg, min(price_sek_kwh) as price_sek_kwh_min, max(price_sek_kwh) as price_sek_kwh_max,
        avg(price_sek_kwh) filter (where extract(hour from ts_local) >= 6 and extract(hour from ts_local) < 22) as price_peak_avg_sek_kwh,
        avg(price_sek_kwh) filter (where extract(hour from ts_local) < 6 or extract(hour from ts_local) >= 22) as price_offpeak_avg_sek_kwh,
        max(eur_sek_rate) as eur_sek_rate
    from {{ ref('entsoe_timeseries') }}
    where metric = 'day_ahead_price'
    group by 1,2
), cheapest as (
    select distinct on (ts_local::date, bidding_zone)
        ts_local::date as date_local, bidding_zone as zone_id,
        extract(hour from ts_local)::int as cheapest_hour_local
    from {{ ref('entsoe_timeseries') }}
    where metric = 'day_ahead_price'
    order by ts_local::date, bidding_zone, price_sek_kwh
), weather as (
    select
        ts_local::date as date_local, zone as zone_id,
        avg(value) filter (where parameter_code='temp')       as temp_c_avg,
        min(value) filter (where parameter_code='temp')       as temp_c_min,
        max(value) filter (where parameter_code='temp')       as temp_c_max,
        avg(value) filter (where parameter_code='wind_speed') as wind_speed_ms_avg,
        sum(value) filter (where parameter_code='precipitation') as precipitation_mm_sum
    from {{ ref('weather_observations_hourly') }}
    group by 1,2
), forecast as (
    select
        ts_local::date as date_local, zone as zone_id,
        max(reference_time) as forecast_reference_time,
        avg(air_temperature) as forecast_temp_c_avg,
        avg(wind_speed) as forecast_wind_ms_avg,
        sum(precipitation_amount_mean) as forecast_precipitation_mm_sum
    from {{ ref('weather_forecast_hourly') }}
    group by 1,2
), hydro as (
    select ts_local::date as date_local, zone as zone_id, avg(value) as discharge_m3s
    from {{ ref('smhi_hydro_observations_daily') }}
    group by 1,2
), tax_fee as (
    select
        period_start as effective_month,
        max(elskatt_sek_kwh) filter (where table_name='hushall' and customer_category='DA') as energy_tax_sek_kwh,
        max(elnatspris_sek_kwh) filter (where table_name='elnat' and customer_category='1' and weighting='viktat') as grid_fee_sek_kwh
    from {{ ref('consumer_prices') }}
    group by 1
)
select
    cal.date_key, zb.zone_key, cal.date_local, cal.effective_month, s.zone_id,
    s.price_eur_mwh_avg, s.price_eur_mwh_min, s.price_eur_mwh_max,
    s.price_sek_kwh_avg, s.price_sek_kwh_min, s.price_sek_kwh_max,
    s.price_peak_avg_sek_kwh, s.price_offpeak_avg_sek_kwh,
    c.cheapest_hour_local, s.eur_sek_rate,
    tf.energy_tax_sek_kwh, tf.grid_fee_sek_kwh,
    0.25 as vat_rate,
    (s.price_sek_kwh_avg + coalesce(tf.energy_tax_sek_kwh,0) + coalesce(tf.grid_fee_sek_kwh,0)) * 1.25 as total_consumer_sek_kwh,
    w.temp_c_avg, w.temp_c_min, w.temp_c_max, w.wind_speed_ms_avg, w.precipitation_mm_sum,
    f.forecast_reference_time, f.forecast_temp_c_avg, f.forecast_wind_ms_avg, f.forecast_precipitation_mm_sum,
    (w.temp_c_avg - f.forecast_temp_c_avg) as temp_forecast_error_c,
    h.discharge_m3s,
    cal.year as obs_year
from spot s
join {{ ref('dim_calendar') }} cal      on cal.date_local = s.date_local
join {{ ref('dim_bidding_zone') }} zb   on zb.zone_id = s.zone_id
left join cheapest c   on c.date_local = s.date_local and c.zone_id = s.zone_id
left join tax_fee tf   on tf.effective_month = cal.effective_month
left join weather w    on w.date_local = s.date_local and w.zone_id = s.zone_id
left join forecast f   on f.date_local = s.date_local and f.zone_id = s.zone_id
left join hydro h      on h.date_local = s.date_local and h.zone_id = s.zone_id
