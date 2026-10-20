with hardware_expected as (
    select fiscal_year_ending, platform_code, region_code, value_units as hardware_units
    from {{ ref('mart_annual_platform_performance') }}
    where metric_code = 'hw_units_sell_in'
      and product_grain = 'hardware'
      and not is_platform_component
),
software_expected as (
    select fiscal_year_ending, platform_code, region_code, value_units as software_units
    from {{ ref('mart_annual_platform_performance') }}
    where metric_code = 'sw_units_sell_in'
      and product_grain = 'software_total'
      and not is_platform_component
),
hardware_mart as (
    select fiscal_year_ending, platform_code, region_code, hardware_units
    from {{ ref('mart_hardware_software_trends') }}
    where hardware_units is not null
),
software_mart as (
    select fiscal_year_ending, platform_code, region_code, software_units
    from {{ ref('mart_hardware_software_trends') }}
    where software_units is not null
),
component_rows as (
    select fiscal_year_ending, platform_code, region_code, hardware_units
    from {{ ref('mart_hardware_software_trends') }} as trends
    where exists (
        select 1
        from {{ ref('mart_annual_platform_performance') }} as annual
        where annual.platform_code = trends.platform_code
          and annual.is_platform_component
    )
)
(
    select * from hardware_expected
    except
    select * from hardware_mart
)
union all
(
    select * from hardware_mart
    except
    select * from hardware_expected
)
union all
(
    select * from software_expected
    except
    select * from software_mart
)
union all
(
    select * from software_mart
    except
    select * from software_expected
)
union all
select * from component_rows
