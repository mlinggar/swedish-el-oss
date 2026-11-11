{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='source_file') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_scb') }}
), raw as (
    select input_file_name, file_modification_time, load_tier, payload
    from ranked where rn = 1
    {% if is_incremental() %}
      and not exists (select 1 from {{ this }} t
        where t.source_file = ranked.input_file_name
          and t.file_modification_time >= ranked.file_modification_time)
    {% endif %}
), cells as (
    select r.input_file_name, r.file_modification_time, r.load_tier, r.payload,
           d.value->'key' as key_arr, v.value as measure_value, (v.ord - 1) as mv_pos
    from raw r
    cross join lateral jsonb_array_elements(r.payload->'data') as d(value)
    cross join lateral jsonb_array_elements(d.value->'values') with ordinality as v(value, ord)
)
select
    c.input_file_name                              as source_file,
    c.load_tier, c.file_modification_time,
    substring(c.input_file_name from '/(elnat|elhandel|hushall)/') as table_name,
    (select jsonb_object_agg(col.value->>'code', kv.value)
       from jsonb_array_elements(c.payload->'columns') with ordinality as col(value, idx)
       join jsonb_array_elements(c.key_arr) with ordinality as kv(value, idx)
         on col.idx = kv.idx)                       as dims,
    (select kv.value
       from jsonb_array_elements(c.payload->'columns') with ordinality as col(value, idx)
       join jsonb_array_elements(c.key_arr) with ordinality as kv(value, idx)
         on col.idx = kv.idx
       where col.value->>'type' = 't' limit 1)      as period,
    (select col.value->>'code'
       from jsonb_array_elements(c.payload->'columns') with ordinality as col(value, idx)
       where col.value->>'type' = 'c' order by col.idx
       offset c.mv_pos limit 1)                     as measure_code,
    (select col.value->>'text'
       from jsonb_array_elements(c.payload->'columns') with ordinality as col(value, idx)
       where col.value->>'type' = 'c' order by col.idx
       offset c.mv_pos limit 1)                     as measure_text,
    c.measure_value, now() as extracted_at
from cells c
