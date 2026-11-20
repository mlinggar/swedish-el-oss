select *
from {{ ref('thermostat_hourly') }}
where is_forecast
  and spot_p10_sek_kwh is not null
  and spot_sek_kwh is not null
  and spot_p90_sek_kwh is not null
  and not (spot_p10_sek_kwh <= spot_sek_kwh and spot_sek_kwh <= spot_p90_sek_kwh)
