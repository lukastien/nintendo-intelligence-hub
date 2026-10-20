with annual as (
    select *
    from {{ ref('mart_annual_platform_performance') }}
    where not is_platform_component
),
hardware as (
    select *
    from annual
    where metric_code = 'hw_units_sell_in'
      and product_grain = 'hardware'
),
software as (
    select *
    from annual
    where metric_code = 'sw_units_sell_in'
      and product_grain = 'software_total'
)
select
    coalesce(hardware.fiscal_year_ending, software.fiscal_year_ending) as fiscal_year_ending,
    coalesce(hardware.period_start, software.period_start) as period_start,
    coalesce(hardware.period_end, software.period_end) as period_end,
    coalesce(hardware.platform_code, software.platform_code) as platform_code,
    coalesce(hardware.platform_name, software.platform_name) as platform_name,
    coalesce(hardware.is_platform_aggregate, software.is_platform_aggregate) as is_platform_aggregate,
    coalesce(hardware.region_code, software.region_code) as region_code,
    coalesce(hardware.region_name, software.region_name) as region_name,
    coalesce(hardware.is_region_aggregate, software.is_region_aggregate) as is_region_aggregate,
    coalesce(hardware.region_layout, software.region_layout) as region_layout,
    hardware.value_units as hardware_units,
    software.value_units as software_units,
    case
        when hardware.value_units is null or software.value_units is null or hardware.value_units = 0 then null
        else software.value_units / hardware.value_units
    end as software_units_per_hardware_unit,
    hardware.value_units is not null and software.value_units is not null as both_metrics_present,
    hardware.source_document_id as hardware_source_document_id,
    software.source_document_id as software_source_document_id,
    coalesce(hardware.source_url, software.source_url) as source_url,
    coalesce(hardware.as_of_date, software.as_of_date) as as_of_date,
    'official_ir' as source_class,
    'annual_flow' as observation_type,
    concat_ws(
        '|',
        coalesce(hardware.fiscal_year_ending, software.fiscal_year_ending)::text,
        coalesce(hardware.platform_code, software.platform_code),
        coalesce(hardware.region_code, software.region_code)
    ) as grain_key
from hardware
full outer join software
    on software.fiscal_year_ending = hardware.fiscal_year_ending
    and software.platform_code = hardware.platform_code
    and software.region_code = hardware.region_code
