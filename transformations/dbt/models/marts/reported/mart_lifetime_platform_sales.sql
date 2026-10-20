with lifetime as (
    select *
    from {{ ref('stg_official__unit_sales') }}
    where period_span = 'life_to_date'
      and product_grain in ('hardware', 'software_total')
      and is_forecast = false
),
ranked as (
    select
        lifetime.*,
        row_number() over (
            partition by metric_code, product_grain, platform_code, region_code
            order by as_of_date desc, source_document_id desc
        ) as as_of_rank
    from lifetime
)
select
    ranked.platform_code,
    ranked.platform_name,
    ranked.is_platform_aggregate,
    ranked.is_platform_component,
    ranked.parent_platform_code,
    not ranked.is_platform_component as include_in_cross_platform_total,
    ranked.metric_code,
    ranked.product_grain,
    ranked.region_code,
    ranked.region_name,
    ranked.is_region_aggregate,
    ranked.measure_value as value_units,
    ranked.source_unit_scale,
    ranked.sales_basis,
    ranked.period_span,
    ranked.fiscal_year_ending,
    ranked.period_start,
    ranked.period_end,
    ranked.as_of_date,
    ranked.as_of_rank = 1 as is_latest_as_of,
    ranked.source_class,
    ranked.source_document_id,
    documents.source_url,
    documents.content_sha256,
    documents.period_label_verbatim,
    ranked.definition_note,
    'point_in_time_cumulative' as observation_type,
    concat_ws(
        '|',
        ranked.source_document_id,
        ranked.as_of_date::text,
        ranked.metric_code,
        ranked.product_grain,
        ranked.platform_code,
        ranked.region_code
    ) as grain_key
from ranked
left join {{ source('meta', 'source_document') }} as documents
    on documents.source_document_id = ranked.source_document_id
