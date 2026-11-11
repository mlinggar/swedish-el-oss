{{ config(materialized='incremental', incremental_strategy='delete+insert',
          unique_key='source_file', schema='bronze') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_smhi_metobs') }}
), raw as (
    select input_file_name, file_modification_time, load_tier, payload
    from ranked where rn = 1
    {% if is_incremental() %}
      and not exists (select 1 from {{ this }} t
        where t.source_file = ranked.input_file_name
          and t.file_modification_time >= ranked.file_modification_time)
    {% endif %}
),
json_branch as (
    select
        r.input_file_name as source_file, r.file_modification_time, r.load_tier,
        case when r.input_file_name like '%gap_%' then 'gap_json'
             else 'latest_day_json' end            as source_format,
        substring(r.input_file_name from '/(SE[1-4])/') as zone,
        case when r.input_file_name like '%temp%'   then 'temp'
             when r.input_file_name like '%wind%'   then 'wind_speed'
             when r.input_file_name like '%precip%' then 'precipitation'
        end                                        as parameter_code,
        r.payload->'station'->>'key'               as station_id,
        r.payload->'station'->>'name'              as station_name,
        r.payload->'parameter'->>'name'            as parameter_name,
        r.payload->'parameter'->>'unit'            as unit,
        to_timestamp((v.value->>'date')::double precision / 1000) as obs_ts,
        v.value->>'value'                          as value,
        v.value->>'quality'                        as quality,
        now()                                      as extracted_at
    from raw r
    cross join lateral jsonb_array_elements(r.payload->'value') as v(value)
    where r.payload ? 'value'
),
csv_branch as (
    select
        a.source_file, a.file_modification_time, a.load_tier,
        'archive_csv'                              as source_format,
        a.zone, a.parameter_code,
        a.station_id, a.station_name, a.parameter_name, a.unit,
        ((a.obs_date || ' ' || a.obs_time || ' +00')::timestamptz) as obs_ts,
        a.value, a.quality,
        now()                                      as extracted_at
    from raw.smhi_metobs_archive_rows a
    {% if is_incremental() %}
    where not exists (select 1 from {{ this }} t
        where t.source_file = a.source_file
          and t.file_modification_time >= a.file_modification_time)
    {% endif %}
)
select * from json_branch
union all
select * from csv_branch
