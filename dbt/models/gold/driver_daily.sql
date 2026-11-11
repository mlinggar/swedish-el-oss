{{ config(materialized='table', schema='gold') }}

with base as (
    select date_local, zone_id, price_sek_kwh_avg,
           temp_c_avg, wind_speed_ms_avg, precipitation_mm_sum, discharge_m3s
    from {{ ref('fact_daily') }}
),
unpivoted as (
    select b.date_local, b.zone_id, b.price_sek_kwh_avg as spot_sek_kwh,
           d.driver_name, d.driver_value
    from base b
    cross join lateral (values
        ('Temp Avg °C',       b.temp_c_avg),
        ('Wind Avg m/s',      b.wind_speed_ms_avg),
        ('Precipitation mm',  b.precipitation_mm_sum),
        ('Discharge m3/s',    b.discharge_m3s)
    ) as d(driver_name, d.driver_value)
),
gas as (
    select f.date_local, f.zone_id, f.price_sek_kwh_avg as spot_sek_kwh,
           'Gas Price SEK/MMBtu' as driver_name,
           g.gas_price_sek_mmbtu as driver_value
    from {{ ref('fact_daily') }} f
    left join lateral (
        select gas_price_sek_mmbtu
        from {{ ref('gas_price_daily_sek') }}
        where gas_date <= f.date_local
        order by gas_date desc limit 1
    ) g on true
)
select * from unpivoted
union all
select * from gas
