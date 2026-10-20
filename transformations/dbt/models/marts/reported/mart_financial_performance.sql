with latest as (
    select distinct on (fiscal_year_ending, metric_code)
        fiscal_year_ending,
        period_start,
        period_end,
        metric_code,
        measure_value,
        entity_code,
        currency_code,
        region_code,
        platform_code,
        source_class,
        source_document_id,
        as_of_date,
        definition_note
    from {{ ref('stg_official__financial_line') }}
    where period_span = 'fiscal_year'
      and is_forecast = false
      and additive_flow = true
    order by fiscal_year_ending, metric_code, as_of_date desc, source_document_id desc
),
pivoted as (
    select
        fiscal_year_ending,
        min(period_start) as period_start,
        min(period_end) as period_end,
        min(entity_code) as entity_code,
        min(currency_code) as currency_code,
        min(region_code) as region_code,
        min(platform_code) as platform_code,
        max(measure_value) filter (where metric_code = 'net_sales_jpy') as net_sales_yen,
        max(measure_value) filter (where metric_code = 'operating_profit_jpy') as operating_profit_yen,
        max(measure_value) filter (where metric_code = 'ordinary_profit_jpy') as ordinary_profit_yen,
        max(measure_value) filter (where metric_code = 'profit_attributable_to_owners_jpy') as profit_attributable_to_owners_yen,
        min(source_class) as source_class,
        min(source_document_id) as source_document_id,
        max(as_of_date) as as_of_date,
        min(definition_note) as definition_note
    from latest
    group by fiscal_year_ending
)
select
    pivoted.fiscal_year_ending,
    pivoted.period_start,
    pivoted.period_end,
    pivoted.entity_code,
    pivoted.currency_code,
    pivoted.region_code,
    pivoted.platform_code,
    pivoted.net_sales_yen,
    pivoted.operating_profit_yen,
    pivoted.ordinary_profit_yen,
    pivoted.profit_attributable_to_owners_yen,
    pivoted.operating_profit_yen / nullif(pivoted.net_sales_yen, 0) as operating_margin_calculated,
    pivoted.ordinary_profit_yen / nullif(pivoted.net_sales_yen, 0) as ordinary_margin_calculated,
    pivoted.profit_attributable_to_owners_yen / nullif(pivoted.net_sales_yen, 0) as profit_margin_calculated,
    'calculated_from_disclosed_annual_flows' as margin_basis,
    pivoted.source_class,
    pivoted.source_document_id,
    documents.source_url,
    documents.content_sha256,
    documents.period_label_verbatim,
    pivoted.as_of_date,
    pivoted.definition_note,
    'annual_flow' as observation_type,
    pivoted.fiscal_year_ending::text as grain_key
from pivoted
left join {{ source('meta', 'source_document') }} as documents
    on documents.source_document_id = pivoted.source_document_id
