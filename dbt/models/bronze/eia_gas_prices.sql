{{ config(schema='bronze') }}
with ranked as (
    select *, row_number() over (
        partition by input_file_name order by file_modification_time desc) as rn
    from {{ source('raw','raw_eia') }}
), raw as (
    select input_file_name, file_modification_time, load_tier, payload
    from ranked where rn = 1
)
select
    r.input_file_name                              as source_file,
    r.load_tier,
    r.file_modification_time,
    (d->>'period')::date                           as obs_date,
    d->>'value'                                    as gas_price,
    d->>'units'                                    as units,
    d->>'series'                                   as series,
    d->>'series-description'                       as series_description,
    d->>'area-name'                                as area_name,
    d->>'product-name'                             as product_name,
    d->>'process-name'                             as process_name,
    d                                              as data_map,
    now()                                          as extracted_at
from raw r
cross join lateral jsonb_array_elements(r.payload->'response'->'data') as d
