{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='source_file') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_entsoe') }}
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
    x.input_file_name                              as source_file,
    x.load_tier, x.file_modification_time,
    r->>'data_item_code'                           as data_item_code,
    (r->'business_dim')                            as business_dim,
    (r->'instance_attr')                           as instance_attr,
    r->>'period_from'                              as period_from,
    r->>'period_to'                                as period_to,
    r->>'resolution'                               as resolution,
    (r->>'point_index')::int                       as point_index,
    ((r->>'period_from')::timestamptz
        + (((r->>'point_index')::int - 1)
           * case r->>'resolution' when 'PT15M' then 900
                                   when 'PT60M' then 3600 else 0 end)
           * interval '1 second')                  as point_ts_utc,
    r->>'value_1'                                  as value_1,
    r->>'value_2'                                  as value_2,
    now()                                          as extracted_at
from raw x
cross join lateral jsonb_array_elements(x.payload->'rows') as r
