{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='source_file') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_ecb') }}
), raw as (
    select input_file_name, file_modification_time, load_tier, payload
    from ranked where rn = 1
    {% if is_incremental() %}
      and not exists (select 1 from {{ this }} t
        where t.source_file = ranked.input_file_name
          and t.file_modification_time >= ranked.file_modification_time)
    {% endif %}
), obs as (
    select r.input_file_name, r.file_modification_time, r.load_tier, r.payload,
           s.key as series_key, o.key as obs_key, o.value as obs_arr
    from raw r
    cross join lateral jsonb_array_elements(r.payload->'dataSets') as d(value)
    cross join lateral jsonb_each(d.value->'series') as s(key, value)
    cross join lateral jsonb_each(s.value->'observations') as o(key, value)
)
select
    o.input_file_name                              as source_file,
    o.load_tier, o.file_modification_time,
    o.obs_arr->>0                                  as rate,
    o.payload->'structure'->'dimensions'->'series'->1->'values'
        ->((split_part(o.series_key,':',2))::int)->>'id'  as currency,
    o.payload->'structure'->'dimensions'->'series'->2->'values'
        ->((split_part(o.series_key,':',3))::int)->>'id'  as currency_denom,
    o.payload->'structure'->'dimensions'->'series'->3->'values'
        ->((split_part(o.series_key,':',4))::int)->>'id'  as exr_type,
    (o.payload->'structure'->'dimensions'->'observation'->0->'values'
        ->(o.obs_key::int)->>'id')::date           as obs_date,
    o.series_key, (o.obs_key::int) as obs_index, now() as extracted_at
from obs o
