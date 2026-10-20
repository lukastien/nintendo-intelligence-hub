with annual_parts as (
    select
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ ref('mart_annual_platform_performance') }}
    where not is_region_aggregate
),
regional as (
    select
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ ref('mart_regional_performance') }}
),
worldwide_rows as (
    select
        fiscal_year_ending,
        metric_code,
        product_grain,
        platform_code,
        region_code,
        value_units
    from {{ ref('mart_regional_performance') }}
    where region_code = 'GLOBAL'
       or region_layout = 'worldwide_total'
)
(
    select * from annual_parts
    except
    select * from regional
)
union all
(
    select * from regional
    except
    select * from annual_parts
)
union all
select * from worldwide_rows
