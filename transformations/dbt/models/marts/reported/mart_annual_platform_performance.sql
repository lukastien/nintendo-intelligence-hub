with staged as (
    select *
    from {{ ref('stg_official__unit_sales') }}
    where period_span = 'fiscal_year'
      and product_grain in ('hardware', 'software_total')
      and is_forecast = false
),
latest as (
    select distinct on (
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code
    )
        *
    from staged
    order by
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        as_of_date desc,
        source_document_id desc
),
grouped as (
    select
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        bool_or(region_code = 'EUR') as has_europe,
        bool_or(region_code = 'OTH_INCL_EUROPE') as has_other_including_europe,
        count(*) filter (where region_code <> 'GLOBAL') as part_count,
        sum(measure_value) filter (where region_code <> 'GLOBAL') as summed_parts,
        max(measure_value) filter (where region_code = 'GLOBAL') as disclosed_global_units,
        max(source_unit_scale) filter (where region_code = 'GLOBAL') as global_scale
    from latest
    group by 1, 2, 3, 4
),
scored as (
    select
        grouped.*,
        case
            when has_europe and has_other_including_europe then null
            when has_europe and part_count = 4 then summed_parts
            when has_other_including_europe and not has_europe and part_count = 3 then summed_parts
            else null
        end as regional_parts_sum,
        case
            when has_europe and has_other_including_europe then 'mixed_region_layout'
            when disclosed_global_units is null then 'incomplete_breakdown'
            when has_europe and part_count = 4 and disclosed_global_units = summed_parts then 'exact'
            when has_europe and part_count = 4
                and abs(disclosed_global_units - summed_parts) <= global_scale then 'within_one_printed_unit'
            when has_europe and part_count = 4 then 'differs'
            when has_other_including_europe and not has_europe and part_count = 3
                and disclosed_global_units = summed_parts then 'exact'
            when has_other_including_europe and not has_europe and part_count = 3
                and abs(disclosed_global_units - summed_parts) <= global_scale then 'within_one_printed_unit'
            when has_other_including_europe and not has_europe and part_count = 3 then 'differs'
            else 'incomplete_breakdown'
        end as reconciliation_status
    from grouped
)
select
    latest.fiscal_year_ending,
    latest.period_start,
    latest.period_end,
    latest.period_span,
    latest.metric_code,
    latest.product_grain,
    latest.platform_code,
    latest.platform_name,
    latest.is_platform_aggregate,
    latest.is_platform_component,
    latest.parent_platform_code,
    not latest.is_platform_component as include_in_cross_platform_total,
    latest.region_code,
    latest.region_name,
    latest.is_region_aggregate,
    case
        when latest.region_code = 'GLOBAL' then 'worldwide_total'
        when scored.has_europe and not scored.has_other_including_europe then 'europe_split'
        when scored.has_other_including_europe and not scored.has_europe then 'europe_inside_other'
        else 'incomplete_regional_breakdown'
    end as region_layout,
    latest.measure_value as value_units,
    latest.source_unit_scale,
    latest.sales_basis,
    scored.disclosed_global_units,
    scored.regional_parts_sum,
    case
        when scored.regional_parts_sum is null then null
        else scored.disclosed_global_units - scored.regional_parts_sum
    end as global_minus_parts,
    scored.reconciliation_status,
    latest.source_class,
    latest.source_document_id,
    documents.source_url,
    documents.content_sha256,
    documents.period_label_verbatim,
    latest.as_of_date,
    latest.definition_note,
    'annual_flow' as observation_type,
    concat_ws(
        '|',
        latest.fiscal_year_ending::text,
        latest.metric_code,
        latest.product_grain,
        latest.platform_code,
        latest.region_code
    ) as grain_key
from latest
inner join scored
    on scored.fiscal_year_ending = latest.fiscal_year_ending
    and scored.metric_code = latest.metric_code
    and scored.product_grain = latest.product_grain
    and scored.platform_code = latest.platform_code
left join {{ source('meta', 'source_document') }} as documents
    on documents.source_document_id = latest.source_document_id
