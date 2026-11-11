{{ config(materialized='table', schema='gold') }}
with dates as (
    select generate_series(date '2022-01-01', date '2030-12-31', interval '1 day')::date as date_local
)
select
    to_char(date_local, 'YYYYMMDD')::int          as date_key,
    date_local,
    date_trunc('month', date_local)::date         as effective_month,
    (extract(dow from date_local))::int + 1       as day_of_week,
    to_char(date_local, 'Day')                    as day_name,
    extract(week from date_local)::int            as week_of_year,
    extract(month from date_local)::int           as month,
    to_char(date_local, 'Month')                  as month_name,
    extract(quarter from date_local)::int         as quarter,
    extract(year from date_local)::int            as year,
    (extract(dow from date_local) in (0,6))       as is_weekend,
    case when extract(month from date_local) in (12,1,2) then 'Winter'
         when extract(month from date_local) in (3,4,5)  then 'Spring'
         when extract(month from date_local) in (6,7,8)  then 'Summer'
         else 'Autumn' end                        as season
from dates
