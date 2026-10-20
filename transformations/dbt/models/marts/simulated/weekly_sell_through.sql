select
    source_class,
    series_name,
    iso_year,
    iso_week,
    week_start,
    sku_code,
    region_code,
    channel_code,
    units,
    disclaimer,
    concat_ws(
        '|',
        series_name,
        iso_year::text,
        iso_week::text,
        sku_code,
        region_code,
        channel_code
    ) as grain_key
from {{ ref('stg_simulated__weekly_sell_through') }}
where source_class = 'simulated_operational'
