with source_rows as (
    select
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ source('raw_official', 'unit_sales_disclosure') }}
    where source_class = 'official_ir'
      and period_span = 'fiscal_year'
      and product_grain in ('hardware', 'software_total')
      and is_forecast = false
),
mart_rows as (
    select
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ ref('mart_annual_platform_performance') }}
)
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
