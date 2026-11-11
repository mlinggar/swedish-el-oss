{{ config(materialized='table', schema='silver') }}
with base as (
    select
        b.table_name,
        coalesce(b.dims->>'Kategorikwh', b.dims->>'Kundkategori')  as customer_category,
        b.dims->>'Avtalstyp'                                       as contract_type,
        b.dims->>'Elomrade'                                        as grid_area,
        b.dims->>'Viktat'                                          as weighting,
        (b.period #>> '{}')                                        as period,
        case b.measure_code
            when '000006WO' then 'handelspris'
            when '000006WP' then 'natpris'
            when '0000070Q' then 'elskatt'
            when '000006WQ' then 'natpris_med_elskatt'
            when '000006WR' then 'moms'
            when '000006WS' then 'totalpris'
            when '000003GO' then 'elhandelspris'
            when '000006QI' then 'elnatspris'
        end                                                        as measure_key,
        case when (b.measure_value #>> '{}') ~ '^-?[0-9]*\.?[0-9]+$'
             then (b.measure_value #>> '{}')::numeric end          as value,
        b.file_modification_time
    from {{ ref('scb_price_measures') }} b
), deduped as (
    select * from (
        select base.*,
               row_number() over (
                   partition by table_name, customer_category, contract_type, grid_area, weighting, period, measure_key
                   order by file_modification_time desc) as rn
        from base where measure_key is not null
    ) t where rn = 1
), pivoted as (
    select table_name, customer_category, contract_type, grid_area, weighting, period,
        max(value) filter (where measure_key='handelspris')         as handelspris_ore_kwh,
        max(value) filter (where measure_key='natpris')             as natpris_ore_kwh,
        max(value) filter (where measure_key='elskatt')             as elskatt_ore_kwh,
        max(value) filter (where measure_key='natpris_med_elskatt') as natpris_med_elskatt_ore_kwh,
        max(value) filter (where measure_key='moms')                as moms_ore_kwh,
        max(value) filter (where measure_key='totalpris')           as totalpris_ore_kwh,
        max(value) filter (where measure_key='elhandelspris')       as elhandelspris_ore_kwh,
        max(value) filter (where measure_key='elnatspris')          as elnatspris_ore_kwh
    from deduped group by 1,2,3,4,5,6
), with_dates as (
    select p.*,
        case when period ~ '^\d{4}H[12]$' then 'half_year'
             when period ~ '^\d{4}M\d{2}$' then 'month' else 'year' end as period_type,
        make_date((substring(period from '^(\d{4})'))::int,
            case when period ~ '^\d{4}M\d{2}$' then (substring(period from '^\d{4}M(\d{2})$'))::int
                 when period ~ '^\d{4}H2$' then 7 else 1 end, 1)   as period_start_base,
        case when period ~ '^\d{4}H[12]$' then 6
             when period ~ '^\d{4}M\d{2}$' then 1 else 12 end      as n_months
    from pivoted p
)
select
    table_name, customer_category, contract_type, grid_area, weighting, period_type,
    g.month_start::date as period_start, period,
    handelspris_ore_kwh, natpris_ore_kwh, elskatt_ore_kwh, natpris_med_elskatt_ore_kwh,
    moms_ore_kwh, totalpris_ore_kwh, elhandelspris_ore_kwh, elnatspris_ore_kwh,
    handelspris_ore_kwh/100.0         as handelspris_sek_kwh,
    natpris_ore_kwh/100.0             as natpris_sek_kwh,
    elskatt_ore_kwh/100.0             as elskatt_sek_kwh,
    natpris_med_elskatt_ore_kwh/100.0 as natpris_med_elskatt_sek_kwh,
    moms_ore_kwh/100.0                as moms_sek_kwh,
    totalpris_ore_kwh/100.0           as totalpris_sek_kwh,
    elhandelspris_ore_kwh/100.0       as elhandelspris_sek_kwh,
    elnatspris_ore_kwh/100.0          as elnatspris_sek_kwh,
    now() as silver_generated_at
from with_dates
cross join lateral generate_series(
    period_start_base::timestamp,
    period_start_base::timestamp + make_interval(months => n_months - 1),
    interval '1 month') as g(month_start)
