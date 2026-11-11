{{ config(materialized='table', schema='gold') }}
with all_stations as (
    select 'smhi_metobs' as data_source, station_id, station_name,
           null as station_owner, parameter_code, zone as zone_id,
           min(ts_utc) as first_ts, max(ts_utc) as last_ts
    from {{ ref('weather_observations_hourly') }}
    group by 1,2,3,4,5,6
    union all
    select 'smhi_hydro', station_id, station_name,
           station_owner, parameter_code, zone,
           min(ts_utc), max(ts_utc)
    from {{ ref('smhi_hydro_observations_daily') }}
    group by 1,2,3,4,5,6
)
select
    row_number() over (order by data_source, station_id, parameter_code) as station_key,
    station_id, station_name, station_owner, data_source, parameter_code, zone_id,
    first_ts, last_ts
from all_stations
