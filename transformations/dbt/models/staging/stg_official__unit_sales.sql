select
    unit_sales.disclosure_id,
    unit_sales.source_document_id,
    unit_sales.source_class,
    unit_sales.metric_code,
    unit_sales.product_grain,
    unit_sales.platform_code,
    coalesce(dim_platform.platform_name, unit_sales.platform_code) as platform_name,
    unit_sales.is_platform_aggregate,
    unit_sales.is_platform_component,
    unit_sales.parent_platform_code,
    unit_sales.region_code,
    coalesce(dim_region.region_name, unit_sales.region_code) as region_name,
    unit_sales.is_region_aggregate,
    unit_sales.game_code,
    unit_sales.fiscal_year_ending,
    unit_sales.period_span,
    unit_sales.fiscal_quarter,
    unit_sales.period_start,
    unit_sales.period_end,
    unit_sales.as_of_date,
    unit_sales.value_units as measure_value,
    unit_sales.source_unit_scale,
    unit_sales.is_forecast,
    unit_sales.is_additive_flow as additive_flow,
    unit_sales.sales_basis,
    unit_sales.definition_note
from {{ source('raw_official', 'unit_sales_disclosure') }} as unit_sales
left join {{ source('ref', 'dim_platform') }} as dim_platform
    on unit_sales.platform_code = dim_platform.platform_code
left join {{ source('ref', 'dim_region') }} as dim_region
    on unit_sales.region_code = dim_region.region_code
where unit_sales.source_class = 'official_ir'
