# Dashboard metrics

Nintendo's fiscal year ends on March 31. FY3/2026 is April 1, 2025 through March 31, 2026. An annual row is a flow over that year. A life-to-date row is a cumulative total on an as-of date and carries no fiscal year.

| Displayed metric | Calculation | Unit | Source |
| --- | --- | --- | --- |
| Worldwide hardware / software | Sum of one annual metric across platform scopes where `include_in_cross_platform_total` is true, region `GLOBAL` | Units | `mart_annual_platform_performance` |
| Comparable year-over-year | (current sum − prior sum) ÷ prior sum, only when the set of reporting platform scopes is identical in both years | Ratio | Same mart |
| Hardware / software trend | Annual `hardware_units` and `software_units` for one platform and region, as reported | Units | `mart_hardware_software_trends` |
| Software per hardware unit | Annual software units ÷ annual hardware units in the same row | Ratio | Same mart |
| Life-to-date snapshot | The disclosed cumulative total for one as-of date, metric, platform, and region | Units | `mart_lifetime_platform_sales` |
| Regional share | One regional row ÷ `disclosed_global_units` for the same platform, metric, and year | Ratio | `mart_regional_performance` |
| Net sales, operating profit, ordinary profit, profit attributable to owners | As disclosed, per fiscal year | JPY | `mart_financial_performance` |
| Operating margin | Operating profit ÷ net sales, same fiscal year | Ratio | Calculated in the mart |
| Net profit margin | Profit attributable to owners ÷ net sales, same fiscal year | Ratio | Calculated in the mart |
| Financial growth | (current − prior) ÷ prior, for consecutive loaded fiscal years | Ratio | `mart_financial_performance` |

## What the metrics are not

- Sell-in is not sell-through and not consumer demand at retail.
- Platform unit sales are not Nintendo of America revenue. Financial rows are consolidated Nintendo Co., Ltd. worldwide results.
- A software-per-hardware ratio of two annual flows is not an installed-base attach rate.
- Margins are calculated. They are not the ratio lines printed on the income sheet.

## Always blank rather than invented

- A year-over-year total when a platform entered or left the reporting set.
- A ratio whose hardware denominator is zero or missing.
- A margin whose net-sales denominator is zero or missing.
- A regional share for an incomplete breakdown, where the overseas split was not printed.
- Any quarterly figure. No `q1`, `q1_q2`, or `q1_q3` columns are loaded, so the quarterly marts are empty and no page charts quarters.

Unavailable metrics are listed on the Financial Intelligence page and in `docs/BUSINESS_METRICS.md`.
