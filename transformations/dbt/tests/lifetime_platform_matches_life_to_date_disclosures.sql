with source_rows as (
    select
        source_document_id,
        as_of_date,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ source('raw_official', 'unit_sales_disclosure') }}
    where source_class = 'official_ir'
      and period_span = 'life_to_date'
      and product_grain in ('hardware', 'software_total')
      and is_forecast = false
),
mart_rows as (
    select
        source_document_id,
        as_of_date,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ ref('mart_lifetime_platform_sales') }}
),
mismatched as (
    (
        select * from source_rows
        except
        select * from mart_rows
    )
    union all
    (
        select * from mart_rows
        except
        select * from source_rows
    )
),
labeled_as_a_year as (
    select
        source_document_id,
        as_of_date,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ ref('mart_lifetime_platform_sales') }}
    where fiscal_year_ending is not null
       or period_start is not null
       or observation_type <> 'point_in_time_cumulative'
)
select * from mismatched
union all
select * from labeled_as_a_year
