{{ config(schema='bronze') }}
select
    x.input_file_name                              as source_file,
    x.load_tier,
    x.file_modification_time,
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
from {{ source('raw','raw_entsoe') }} x
cross join lateral jsonb_array_elements(x.payload->'rows') as r
