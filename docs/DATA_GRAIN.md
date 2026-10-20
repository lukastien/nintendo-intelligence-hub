# Data grain

Nintendo's fiscal year ends on March 31. FY3/2026 runs from April 1, 2025 through March 31, 2026. Q1 is April-June, Q2 is July-September, Q3 is October-December, and Q4 is January-March.

An earnings narrative can call the nine-month period "the third quarter" while the column header is `Q1-Q3`, meaning April 1 through December 31. A chart point labeled Q3 is October 1 through December 31. This warehouse stores the column's span. The span name, not the prose around it, chooses the grain.

## Period spans

| `period_span` | Inclusive window for FY3/2026 | What the value means |
| --- | --- | --- |
| `q1` | 2025-04-01 to 2025-06-30 | Year-to-date, and also the first quarter |
| `q1_q2` | 2025-04-01 to 2025-09-30 | First-half cumulative |
| `q1_q3` | 2025-04-01 to 2025-12-31 | Nine-month cumulative |
| `fiscal_year` | 2025-04-01 to 2026-03-31 | Full-year cumulative |
| `quarter` plus `fiscal_quarter` | One quarter only | A single-quarter disclosure |
| `life_to_date` | As-of date in `period_end` | Accumulated total, with the fiscal year left empty |
| `forecast_fiscal_year` | Same window as `fiscal_year` | Company forecast, `is_forecast` true |

Year-to-date rows leave `fiscal_quarter` empty. Putting `3` on a `q1_q3` row is rejected, in Python and in PostgreSQL. A row labeled `quarter` / `3` must run from October 1 through December 31. April 1 through December 31 fails that check. `as_of_date` is on or after `period_end`. An earlier as-of date is rejected in Python and in PostgreSQL.

`ref.period_bounds_ok` and `nih.periods.expected_period_bounds` encode the same windows. The warehouse test compares them.

## How a quarter is derived

The incremental marts accept official, additive, actual year-to-date spans: `q1`, `q1_q2`, `q1_q3`, and `fiscal_year`.

| Fiscal quarter | Closing span | Opening span | Method |
| --- | --- | --- | --- |
| Q1 | `q1` | none | `ytd_equals_quarter`, marked as disclosed |
| Q2 | `q1_q2` | `q1` | `difference_of_ytd` |
| Q3 | `q1_q3` | `q1_q2` | `difference_of_ytd` |
| Q4 | `fiscal_year` | `q1_q3` | `difference_of_ytd` |

If the previous span is missing, that quarter is a gap. A missing half-year span blocks Q3. Q4 still derives when both the nine-month total and the fiscal-year total are present, because Q4 opens from the nine-month span. A full-year total alone does not become four quarters. A negative difference is stored and flagged `restatement_or_revision`. When two documents disagree on the same span, the later `as_of_date` is kept and the quarter is flagged.

Single-quarter disclosures, life-to-date totals, forecasts, and balance-sheet stocks stay on the disclosure grain. They are not subtracted from year-to-date rows.

### Synthetic walk-through

These quantities are invented so the arithmetic is visible. They are not Nintendo results.

| Printed span | Value |
| --- | --- |
| `q1` | 1,000 |
| `q1_q2` | 1,400 |
| `q1_q3` | absent |
| `fiscal_year` | 2,000 |

Derived result:

| Quarter | Incremental value | Why |
| --- | --- | --- |
| Q1 | 1,000 | The Q1 year-to-date total is the quarter |
| Q2 | 400 | 1,400 minus 1,000 |
| Q3 | not produced | The nine-month span is absent, so Q3 has no adjacent opening total |
| Q4 | not produced | Q4 needs the nine-month total as its opening span |

## Fact tables

### `raw_official.unit_sales_disclosure`

Grain: one Nintendo-disclosed sell-in measure for one source document, fiscal year (empty for life-to-date), metric, platform scope, region scope, optional title, and period span. The same document can hold the prior fiscal year and the current fiscal year.

`value_units` equals `source_value_as_printed * source_unit_scale`. Historical regional tables are printed in units of ten thousand, so the scale is stored beside the printed number. Sell-in means sales by the Nintendo group to outside parties, including direct-to-consumer and downloadable software, as described in the company's explanatory notes.

Software unit sales, as defined in those notes, include packaged software and the downloadable edition of packaged software, including bundles. They exclude download-only software and add-on content. The row keeps a `definition_note` because platform-family treatment of editions and upgrade packs is part of the disclosure.

A family total and an "of which" model are different `platform_code` values. `NSW_FAMILY` already includes `NSW`, `NSOLED`, and `NSLITE`. The collision monitor flags a period that contains both the family and a component.

`GLOBAL` already includes the regional rows. The same monitor flags a period that contains both.

Title rows use `product_grain = software_title`. A title total on the top-selling list is life-to-date unless the column header limits it to a fiscal span. Life-to-date title totals are excluded from the incremental mart.

### `raw_official.financial_line`

Grain: one consolidated Nintendo Co., Ltd. statement amount for one source document, fiscal year (empty for life-to-date), metric, region scope, and period span. The same document can hold two fiscal years.

`entity_code` is `nintendo_co_ltd_consolidated`. `platform_code` is `CONSOLIDATED`. Currency is JPY. `amount_yen` equals the printed amount times `printed_scale` (`ones`, `thousands`, `millions`, or `billions`).

Geographical sales remain consolidated regional sales. The Americas region is not a Nintendo of America profit-and-loss statement.

Income-statement lines are additive flows and can use the same year-to-date difference as unit sales. `total_assets_jpy` is a point-in-time stock. A financial row enters the incremental mart only when both `is_additive_flow` on the row and `additive_flow` on the metric are true. Either flag false keeps the row on the disclosure grain. Dedicated-platform net sales include hardware, accessories, amiibo, download-only software, add-on content, and membership services, so yen rows and software-unit rows stay in separate facts.

### `mart_reported.unit_sales_incremental_quarter`

Grain: one derived fiscal quarter per fiscal year, metric, product grain, platform scope, region scope, and optional title.

Official year-to-date actuals only. `derivation_method` is `ytd_equals_quarter` or `difference_of_ytd`. Q2, Q3, and Q4 from this mart have `is_as_disclosed` false.

### `mart_reported.financial_flow_incremental_quarter`

Grain: one derived fiscal quarter per fiscal year, additive statement line, and region scope.

Same span rules. Stocks, forecasts, and life-to-date rows are absent.

### `mart_reported.mart_annual_platform_performance`

Grain: one fiscal-year sell-in flow for one metric, platform scope, and region scope.

Hardware and software-total rows only. Life-to-date totals and software-title rankings stay out. `observation_type` is `annual_flow`. A family row and a component row are both present and are not additive. `GLOBAL` is not additive with the regional rows. `reconciliation_status` compares a disclosed worldwide total with the sum of one region layout. It does not rewrite either figure.

### `mart_reported.mart_hardware_software_trends`

Grain: one fiscal year, one non-component platform, and one region.

Annual hardware units and annual software units sit on the same row. A missing side stays null. The software-per-hardware ratio is calculated only when both sides exist and hardware is not zero.

### `mart_reported.mart_regional_performance`

Grain: the annual grain without the `GLOBAL` row.

`disclosed_global_units` repeats the worldwide total. `europe_split` and `europe_inside_other` are different region definitions.

### `mart_reported.mart_lifetime_platform_sales`

Grain: one life-to-date hardware or software-total observation for one source document, as-of date, metric, platform scope, and region.

`observation_type` is `point_in_time_cumulative`. Two as-of dates remain two rows. `is_latest_as_of` marks the later document and does not delete the earlier one. Title rankings are not in this mart.

### `mart_reported.mart_financial_performance`

Grain: one consolidated fiscal year.

The four yen columns are the disclosed annual flows. Margin columns are calculated from those flows. There is no region split, platform split, or quarter.

### `mart_reported.financial_line_as_disclosed`

Grain: the same grain as `raw_official.financial_line`.

This view preserves the printed span. It is the place to read a nine-month net-sales total without treating it as the October-December quarter.

### `raw_simulated.weekly_sell_through`

Grain: one synthetic sell-through quantity per ISO week, synthetic SKU, synthetic region, and synthetic channel.

`source_class` is `simulated_operational`. Series names start with `synthetic_`, SKUs with `SYN_`, and regions and channels with `SIM_`. Every row carries a disclaimer. The bootstrap series is `synthetic_demo_weekly`. Its quantities are a fixed arithmetic pattern for pipeline tests.

### `mart_simulated.weekly_sell_through`

Grain: the same grain as the simulated landing table, restricted to rows that pass those labels.

Forecasting and z-score alerts read this population. They reject `official_ir`.

## Dimensions

| Table | Grain |
| --- | --- |
| `ref.dim_date` | One calendar date, with Nintendo fiscal attributes |
| `ref.dim_platform` | One platform scope. Families and component models are separate rows |
| `ref.dim_region` | One IR geography, plus `GLOBAL` |
| `ref.dim_game` | One game identifier. No sales |
| `ref.bridge_game_platform` | One game and platform compatibility. No sales |
| `ref.dim_metric` | One metric definition, including whether it is an additive flow |

## Control tables

`meta.source_document` is one retrieved document or generator run. Official rows keep the verbatim period label. `meta.load_audit` is one bootstrap or load action. Neither table is a sales fact.

`nih ingest` loads official disclosures into the fact tables. `nih init-db` still does not insert those measures. `ref.dim_date` covers April 1, 1990 through March 31, 2028.
