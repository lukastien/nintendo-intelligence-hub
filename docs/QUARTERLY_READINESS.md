# Quarterly readiness

`mart_reported.unit_sales_incremental_quarter` and `mart_reported.financial_flow_incremental_quarter` have no rows. That is the current contents of the official facts, not a failed derivation.

## What the derivation needs

A fiscal quarter is produced only from adjacent cumulative spans inside one fiscal year:

| Quarter | Required closing span | Required opening span |
| --- | --- | --- |
| Q1 | `q1` | none |
| Q2 | `q1_q2` | `q1` |
| Q3 | `q1_q3` | `q1_q2` |
| Q4 | `fiscal_year` | `q1_q3` |

A `fiscal_year` row with no `q1_q3` row does not become four quarters. Life-to-date rows are not inputs.

## What is loaded

| Fact | Spans present | Spans absent |
| --- | --- | --- |
| `hw_units_sell_in` | `fiscal_year`, `life_to_date` | `q1`, `q1_q2`, `q1_q3`, `quarter`, `forecast_fiscal_year` |
| `sw_units_sell_in` for platform totals and titles | `fiscal_year`, `life_to_date` | `q1`, `q1_q2`, `q1_q3`, `quarter`, `forecast_fiscal_year` |
| `net_sales_jpy` | `fiscal_year` | `q1`, `q1_q2`, `q1_q3`, `quarter`, `life_to_date`, `forecast_fiscal_year` |
| `operating_profit_jpy` | `fiscal_year` | same as net sales |
| `ordinary_profit_jpy` | `fiscal_year` | same as net sales |
| `profit_attributable_to_owners_jpy` | `fiscal_year` | same as net sales |

The historical sales workbook's year columns are already full fiscal years. Its other column is life-to-date. The income workbook's year columns are full fiscal years. The dedicated unit page and the title pages are life-to-date. None of those files prints Q1, the first half, the nine-month total, or a single quarter.

## What would have to be added

Quarterly rows require a public file whose column header is one of those spans, for each metric that should become quarterly. The practical sources are the quarterly financial-results PDFs and the Euroland supplementary unit-sales file linked from the IR site. Those files are not downloaded or parsed. Until a reviewed load writes `q1`, `q1_q2`, or `q1_q3` rows, the incremental marts stay empty.

No annual total in this warehouse is divided into quarters.
