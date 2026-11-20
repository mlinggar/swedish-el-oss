select *
from {{ ref('thermostat_hourly') }}
where ts_local is null or zone is null
