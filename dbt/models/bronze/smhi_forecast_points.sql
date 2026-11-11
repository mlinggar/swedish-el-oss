{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='source_file') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_smhi_forecast') }}
), raw as (
    select input_file_name, file_modification_time, load_tier, payload
    from ranked where rn = 1
    {% if is_incremental() %}
      and not exists (select 1 from {{ this }} t
        where t.source_file = ranked.input_file_name
          and t.file_modification_time >= ranked.file_modification_time)
    {% endif %}
)
select
    r.input_file_name                              as source_file,
    r.load_tier, r.file_modification_time,
    substring(r.input_file_name from '/(SE[1-4])/') as zone,
    (r.payload->>'referenceTime')::timestamptz     as reference_time,
    (t.value->>'time')::timestamptz                as forecast_ts,
    (t.value->>'intervalParametersStartTime')::timestamptz as interval_parameters_start,
    (r.payload->'geometry'->'coordinates'->>1)::double precision as lat,
    (r.payload->'geometry'->'coordinates'->>0)::double precision as lon,
    t.value->'data'                                as data_map, now() as extracted_at
from raw r
cross join lateral jsonb_array_elements(r.payload->'timeSeries') as t(value)
