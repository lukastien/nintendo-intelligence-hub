select grain_key
from {{ ref('mart_annual_platform_performance') }}
where source_class <> 'official_ir'
   or platform_code like 'SYN%'
   or region_code like 'SIM%'
   or region_code like 'SYN%'
union all
select grain_key
from {{ ref('mart_hardware_software_trends') }}
where source_class <> 'official_ir'
   or platform_code like 'SYN%'
   or region_code like 'SIM%'
   or region_code like 'SYN%'
union all
select grain_key
from {{ ref('mart_financial_performance') }}
where source_class <> 'official_ir'
   or platform_code like 'SYN%'
   or region_code like 'SIM%'
union all
select grain_key
from {{ ref('mart_lifetime_platform_sales') }}
where source_class <> 'official_ir'
   or platform_code like 'SYN%'
   or region_code like 'SIM%'
   or region_code like 'SYN%'
union all
select grain_key
from {{ ref('mart_regional_performance') }}
where source_class <> 'official_ir'
   or platform_code like 'SYN%'
   or region_code like 'SIM%'
   or region_code like 'SYN%'
union all
select grain_key
from {{ ref('unit_sales_incremental_quarter') }}
where source_class <> 'official_ir'
   or platform_code like 'SYN%'
   or region_code like 'SIM%'
union all
select grain_key
from {{ ref('financial_flow_incremental_quarter') }}
where source_class <> 'official_ir'
   or platform_code <> 'CONSOLIDATED'
union all
select grain_key
from {{ ref('financial_line_as_disclosed') }}
where source_class <> 'official_ir'
