select ts_local, zone, count(*) as n
from {{ ref('thermostat_hourly') }}
group by 1, 2
having count(*) > 1
