select
    financial_line.financial_line_id,
    financial_line.source_document_id,
    financial_line.source_class,
    financial_line.metric_code,
    'financial_line' as product_grain,
    financial_line.platform_code,
    financial_line.region_code,
    null::text as game_code,
    financial_line.fiscal_year_ending,
    financial_line.period_span,
    financial_line.fiscal_quarter,
    financial_line.period_start,
    financial_line.period_end,
    financial_line.as_of_date,
    financial_line.amount_yen as measure_value,
    financial_line.amount_as_printed,
    financial_line.printed_scale,
    financial_line.currency_code,
    financial_line.entity_code,
    financial_line.is_forecast,
    (
        financial_line.is_additive_flow
        and coalesce(dim_metric.additive_flow, false)
    ) as additive_flow
from {{ source('raw_official', 'financial_line') }} as financial_line
left join {{ source('ref', 'dim_metric') }} as dim_metric
    on financial_line.metric_code = dim_metric.metric_code
where financial_line.source_class = 'official_ir'
  and financial_line.entity_code = 'nintendo_co_ltd_consolidated'
