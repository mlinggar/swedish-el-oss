{{ config(materialized='table', schema='gold') }}
select
    cal.date_local, cal.effective_month, cal.day_of_week, cal.day_name, cal.week_of_year,
    cal.month, cal.month_name, cal.quarter, cal.year, cal.is_weekend, cal.season,
    fd.zone_id, zb.zone_name, zb.region,
    fd.price_sek_kwh_avg, fd.price_sek_kwh_min, fd.price_sek_kwh_max,
    fd.price_peak_avg_sek_kwh, fd.price_offpeak_avg_sek_kwh, fd.cheapest_hour_local,
    fd.eur_sek_rate, fd.energy_tax_sek_kwh, fd.grid_fee_sek_kwh, fd.vat_rate, fd.total_consumer_sek_kwh,
    fd.temp_c_avg, fd.temp_c_min, fd.temp_c_max,
    fd.forecast_temp_c_avg, fd.forecast_wind_ms_avg, fd.forecast_precipitation_mm_sum, fd.temp_forecast_error_c,
    fd.discharge_m3s, fd.obs_year
from {{ ref('fact_daily') }} fd
join {{ ref('dim_calendar') }} cal    on cal.date_key = fd.date_key
join {{ ref('dim_bidding_zone') }} zb on zb.zone_key = fd.zone_key
where fd.zone_id in ('SE3','SE4')
