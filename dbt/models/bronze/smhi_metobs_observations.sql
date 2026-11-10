{{ config(schema='bronze') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_smhi_metobs') }}
), raw as (
    select input_file_name, file_modification_time, load_tier, payload
    from ranked where rn = 1
),
json_branch as (
    select
        r.input_file_name, r.file_modification_time, r.load_tier,
        case when r.input_file_name like '%gap_%' then 'gap_json'
             else 'latest_day_json' end            as source_format,
        substring(r.input_file_name from '/(SE[1-4])/') as zone,
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
), csv_branch as (
    select
        r.input_file_name, r.file_modification_time, r.load_tier,
        'archive_csv'                              as source_format,
        substring(r.input_file_name from '/(SE[1-4])/') as zone,
        r.payload->'header'->>'Stationsnummer'     as station_id,
        r.payload->'header'->>'Stationsnamn'       as station_name,
        r.payload->'header'->>'Parameternamn'      as parameter_name,
        r.payload->'header'->>'Enhet'              as unit,
        ((rw->>'Datum') || ' ' || (rw->>'Tid UTC') || ' +00')::timestamptz as obs_ts,
        rw->>'value'                               as value,
        rw->>'Kvalitet'                            as quality,
        now()                                      as extracted_at
    from raw r
    cross join lateral jsonb_array_elements(r.payload->'rows') as rw
    where r.payload ? 'rows'
)
select * from json_branch
union all
select * from csv_branch
