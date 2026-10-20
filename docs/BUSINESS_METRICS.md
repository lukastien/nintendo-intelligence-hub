# Business metrics

These definitions match the rows loaded from Nintendo IR. A metric that is not in this list is not in the analytics marts.

Nintendo's fiscal year ends on March 31. FY3/2026 is April 1, 2025 through March 31, 2026. An annual row uses that window. A life-to-date row has no fiscal year. It is the cumulative total printed for the document's as-of date.

## Disclosed unit metrics

| Code | What it measures | Unit | Where it can be read |
| --- | --- | --- | --- |
| `hw_units_sell_in` | Hardware sell-in for one platform scope | Units, already scaled from the printed figure | Annual mart, lifetime mart, trend mart |
| `sw_units_sell_in` | Software sell-in. On a platform row this is the platform total. On a title row it is that title only | Units | Platform totals are in the annual, lifetime, and trend marts. Title rows stay in `raw_official.unit_sales_disclosure` |

Sell-in is sales by the Nintendo group to outside parties, including direct-to-consumer and downloadable software, as described on the source. It is not sell-through, and it is not a retail inventory movement.

Software units, as defined in the historical notes, include packaged software and the downloadable edition of packaged software, including bundles. They exclude download-only software and add-on content. A platform software total already includes the titles on that platform. Adding a top-title row to the platform total double-counts those titles.

`value_units` equals the printed number times `source_unit_scale`. The historical workbook is printed in units of ten thousand, so the scale is 10,000. The dedicated unit page and the title pages are printed per million of the unit, so the scale is 1,000,000.

## Disclosed financial metrics

All four are consolidated Nintendo Co., Ltd. flows, worldwide, in yen. They are not a platform split and not a Nintendo of America statement.

| Code | Mart column | Meaning |
| --- | --- | --- |
| `net_sales_jpy` | `net_sales_yen` | Annual consolidated net sales |
| `operating_profit_jpy` | `operating_profit_yen` | Annual operating profit |
| `ordinary_profit_jpy` | `ordinary_profit_yen` | Annual ordinary profit |
| `profit_attributable_to_owners_jpy` | `profit_attributable_to_owners_yen` | Annual profit attributable to owners of the parent |

`amount_yen` equals the printed number times one million, because the income sheet says millions of yen.

## Calculated fields

These are not printed lines. The income sheet's ratio rows were not loaded.

| Column | Definition |
| --- | --- |
| `software_units_per_hardware_unit` | Annual software units divided by annual hardware units for the same platform scope, region, and fiscal year. Null when either metric is missing or hardware is zero |
| `operating_margin_calculated` | Operating profit divided by net sales |
| `ordinary_margin_calculated` | Ordinary profit divided by net sales |
| `profit_margin_calculated` | Profit attributable to owners divided by net sales |

`margin_basis` is `calculated_from_disclosed_annual_flows`.

## How to add rows

| Question | Safe filter |
| --- | --- |
| Hardware or software across platforms for one year and one region | `include_in_cross_platform_total` and one `region_code` |
| One platform family, including every model | The family row only, for example `NSW_FAMILY`. Leave `NSW`, `NSOLED`, and `NSLITE` out |
| One model inside a family | The component row only. Leave the family row out |
| Worldwide | `region_code = 'GLOBAL'` |
| Japan, the Americas, Europe, and Other | `region_layout = 'europe_split'`. Do not add `OTH_INCL_EUROPE` |
| Japan, the Americas, and Other-including-Europe | `region_layout = 'europe_inside_other'` |
| Latest life-to-date snapshot | `is_latest_as_of`. Do not sum that row with an earlier as-of date |

`GLOBAL` already includes the regional rows. `OTH_INCL_EUROPE` already includes Europe. `NSW_FAMILY` already includes the Switch, OLED, and Lite models. The same pattern applies to the DS, 3DS, and Game Boy Advance families.

## Not available as metrics

- Fiscal-quarter unit sales or fiscal-quarter income
- Sell-through, channel sales, or inventory
- Dedicated-platform net sales in yen, by platform
- Gross profit, profit before tax, and foreign-exchange gains or losses
- Printed profit ratios
- A Nintendo of America management profit-and-loss statement
- Annual sales of one software title
- A forecast
