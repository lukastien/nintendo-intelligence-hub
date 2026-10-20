# Example queries

The views are in schema `mart_reported`. Each query reads one observation type. Annual flows and life-to-date totals are separate results.

## Switch family hardware by fiscal year, worldwide

```sql
select
    fiscal_year_ending,
    period_start,
    period_end,
    value_units,
    source_document_id,
    as_of_date
from mart_reported.mart_annual_platform_performance
where platform_code = 'NSW_FAMILY'
  and metric_code = 'hw_units_sell_in'
  and region_code = 'GLOBAL'
order by fiscal_year_ending;
```

## Hardware and software together for non-component platforms

```sql
select
    fiscal_year_ending,
    platform_code,
    hardware_units,
    software_units,
    software_units_per_hardware_unit
from mart_reported.mart_hardware_software_trends
where region_code = 'GLOBAL'
  and both_metrics_present
order by platform_code, fiscal_year_ending;
```

`software_units_per_hardware_unit` is blank when either annual figure is missing.

## Consolidated income and calculated margins

```sql
select
    fiscal_year_ending,
    net_sales_yen,
    operating_profit_yen,
    ordinary_profit_yen,
    profit_attributable_to_owners_yen,
    operating_margin_calculated,
    profit_margin_calculated,
    source_url
from mart_reported.mart_financial_performance
order by fiscal_year_ending;
```

The margin columns are divisions of the disclosed yen amounts. They are not the ratio rows on the income sheet.

## Latest life-to-date platform totals

```sql
select
    platform_code,
    metric_code,
    region_code,
    value_units,
    as_of_date,
    source_document_id
from mart_reported.mart_lifetime_platform_sales
where is_latest_as_of
  and region_code = 'GLOBAL'
  and include_in_cross_platform_total
order by platform_code, metric_code;
```

Leave `is_latest_as_of` off to see every snapshot. Do not add two as-of dates for the same platform.

## Regional rows that use one region definition

```sql
select
    fiscal_year_ending,
    platform_code,
    metric_code,
    region_code,
    value_units,
    reconciliation_status,
    global_minus_parts
from mart_reported.mart_regional_performance
where platform_code = 'NSW_FAMILY'
  and metric_code = 'hw_units_sell_in'
  and region_layout = 'europe_split'
  and include_in_cross_platform_total
order by fiscal_year_ending, region_code;
```

`europe_split` is Japan, the Americas, Europe, and Other. `europe_inside_other` is the older layout, where Europe is inside Other. Those layouts are not added to each other. `reconciliation_status = 'exact'` means the four or three parts equal the disclosed worldwide total.
