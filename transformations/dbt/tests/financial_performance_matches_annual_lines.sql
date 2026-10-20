with source_rows as (
    select
        fiscal_year_ending,
        metric_code,
        amount_yen
    from {{ source('raw_official', 'financial_line') }}
    where source_class = 'official_ir'
      and period_span = 'fiscal_year'
      and is_forecast = false
      and metric_code in (
          'net_sales_jpy',
          'operating_profit_jpy',
          'ordinary_profit_jpy',
          'profit_attributable_to_owners_jpy'
      )
),
mart_rows as (
    select fiscal_year_ending, 'net_sales_jpy' as metric_code, net_sales_yen as amount_yen
    from {{ ref('mart_financial_performance') }}
    where net_sales_yen is not null
    union all
    select fiscal_year_ending, 'operating_profit_jpy', operating_profit_yen
    from {{ ref('mart_financial_performance') }}
    where operating_profit_yen is not null
    union all
    select fiscal_year_ending, 'ordinary_profit_jpy', ordinary_profit_yen
    from {{ ref('mart_financial_performance') }}
    where ordinary_profit_yen is not null
    union all
    select fiscal_year_ending, 'profit_attributable_to_owners_jpy', profit_attributable_to_owners_yen
    from {{ ref('mart_financial_performance') }}
    where profit_attributable_to_owners_yen is not null
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
