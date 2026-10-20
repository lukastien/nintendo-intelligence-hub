select
    weekly_sell_through_id,
    source_class,
    series_name,
    iso_year,
    iso_week,
    week_start,
    sku_code,
    region_code,
    channel_code,
    units,
    disclaimer
from {{ source('raw_simulated', 'weekly_sell_through') }}
where source_class = 'simulated_operational'
  and series_name like 'synthetic_%'
  and sku_code like 'SYN_%'
  and region_code like 'SIM_%'
