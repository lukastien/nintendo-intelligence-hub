select
    disclosure_id,
    source_document_id,
    source_class,
    metric_code,
    product_grain,
    platform_code,
    region_code,
    game_code,
    fiscal_year_ending,
    period_span,
    fiscal_quarter,
    period_start,
    period_end,
    as_of_date,
    value_units as measure_value,
    is_forecast,
    is_additive_flow as additive_flow,
    sales_basis
from {{ source('raw_official', 'unit_sales_disclosure') }}
where source_class = 'official_ir'
