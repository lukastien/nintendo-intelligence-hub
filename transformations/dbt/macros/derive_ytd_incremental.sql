{# PostgreSQL derivation of adjacent year-to-date spans.
   Q1 is the quarter. Later quarters require the previous span.
   Missing spans are omitted. The Python contract in nih.periods also returns gaps.
#}
{% macro derive_ytd_incremental(staging_model) %}
with staged as (
    select *
    from {{ ref(staging_model) }}
    where source_class = 'official_ir'
      and is_forecast = false
      and additive_flow = true
      and period_span in ('q1', 'q1_q2', 'q1_q3', 'fiscal_year')
      and measure_value is not null
),
versions as (
    select
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        coalesce(game_code, '') as game_key,
        period_span,
        count(distinct measure_value) as value_versions
    from staged
    group by 1, 2, 3, 4, 5, 6, 7
),
versioned as (
    select
        staged.*,
        versions.value_versions
    from staged
    inner join versions
        on versions.fiscal_year_ending is not distinct from staged.fiscal_year_ending
        and versions.metric_code = staged.metric_code
        and versions.product_grain = staged.product_grain
        and versions.platform_code = staged.platform_code
        and versions.region_code = staged.region_code
        and versions.game_key = coalesce(staged.game_code, '')
        and versions.period_span = staged.period_span
),
latest as (
    select distinct on (
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        coalesce(game_code, ''),
        period_span
    )
        *
    from versioned
    order by
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        coalesce(game_code, ''),
        period_span,
        as_of_date desc,
        source_document_id desc
),
ordered as (
    select
        latest.*,
        case period_span
            when 'q1' then 1
            when 'q1_q2' then 2
            when 'q1_q3' then 3
            when 'fiscal_year' then 4
        end as span_end_quarter,
        lag(measure_value) over w as prior_value,
        lag(
            case period_span
                when 'q1' then 1
                when 'q1_q2' then 2
                when 'q1_q3' then 3
                when 'fiscal_year' then 4
            end
        ) over w as prior_end_quarter,
        lag(source_document_id) over w as prior_source_document_id
    from latest
    window w as (
        partition by
            fiscal_year_ending,
            metric_code,
            product_grain,
            platform_code,
            region_code,
            coalesce(game_code, '')
        order by
            case period_span
                when 'q1' then 1
                when 'q1_q2' then 2
                when 'q1_q3' then 3
                when 'fiscal_year' then 4
            end
    )
)
select
    fiscal_year_ending,
    span_end_quarter as fiscal_quarter,
    metric_code,
    product_grain,
    platform_code,
    region_code,
    game_code,
    source_class,
    case
        when span_end_quarter = 1 then measure_value
        else measure_value - prior_value
    end as incremental_value,
    case
        when span_end_quarter = 1 then 0
        else prior_value
    end as opening_ytd_value,
    measure_value as closing_ytd_value,
    case
        when span_end_quarter = 1 then 'ytd_equals_quarter'
        else 'difference_of_ytd'
    end as derivation_method,
    case
        when span_end_quarter = 1 then true
        else false
    end as is_as_disclosed,
    case
        when value_versions > 1
            or (span_end_quarter > 1 and measure_value - prior_value < 0)
            then 'restatement_or_revision'
        else 'ok'
    end as quality_flag,
    source_document_id as closing_source_document_id,
    prior_source_document_id as opening_source_document_id,
    concat_ws(
        '|',
        fiscal_year_ending::text,
        span_end_quarter::text,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        coalesce(game_code, '')
    ) as grain_key
from ordered
where span_end_quarter = 1
   or prior_end_quarter = span_end_quarter - 1
{% endmacro %}
