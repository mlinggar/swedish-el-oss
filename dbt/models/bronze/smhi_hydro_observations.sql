{{ config(schema='bronze') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_smhi_hydro') }}
), raw as (
    select input_file_name, file_modification_time, load_tier, payload
    from ranked where rn = 1
)
select
    r.input_file_name                              as source_file,
    r.load_tier,
    r.file_modification_time,
    case when r.input_file_name like '%historical%' then 'historical_json'
         else 'latest_day_json' end                as source_format,
    substring(r.input_file_name from '/(SE[1-4])/') as zone,
    r.payload->'station'->>'key'                   as station_id,
    r.payload->'station'->>'name'                  as station_name,
    r.payload->'station'->>'owner'                 as station_owner,
    r.payload->'station'->>'measuringStations'     as station_measuring_points,
    'discharge'                                    as parameter_code,
    r.payload->'parameter'->>'key'                 as parameter_key,
    r.payload->'parameter'->>'name'                as parameter_name,
    r.payload->'parameter'->>'unit'                as unit,
    r.payload->'period'->>'key'                    as period_key,
    to_timestamp((v.value->>'date')::double precision / 1000) as obs_ts,
    v.value->>'value'                              as value,
    v.value->>'quality'                            as quality,
    (r.payload->>'updated')::bigint                as updated_epoch_ms,
    now()                                          as extracted_at
from raw r
cross join lateral jsonb_array_elements(r.payload->'value') as v(value)
