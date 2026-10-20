# Data dictionary

Cleaned official rows are CSV files in `data/cleaned/nintendo/`. One file is one source document. A sibling `*_rejected.csv` lists cells that were not loaded. The header is `ingestion.records.CLEANED_COLUMNS`.

| Column | Meaning |
| --- | --- |
| `source_document_id` | Stable id for one retrieved file or page, including its as-of date |
| `source_url` | Page or file URL the bytes came from |
| `source_class` | `official_ir` for Nintendo files. Licensed files stay in a separate directory |
| `publisher` | `Nintendo Co., Ltd.` for official files |
| `retrieved_at` | UTC timestamp of the ingestion run |
| `content_sha256` | SHA-256 of the raw file |
| `metric_code` | Code from `config/metrics.yaml` |
| `measurement_type` | `life_to_date_sell_in`, `fiscal_year_sell_in`, `cumulative_sell_in`, `single_quarter_sell_in`, or `consolidated_yen` |
| `product_grain` | `hardware`, `software_total`, `software_title`, or `financial_line` |
| `platform_code` | Warehouse platform code. Family totals and "of which" models use different codes |
| `platform_name_verbatim` | Name printed on the source |
| `is_platform_aggregate` | True for a family total such as the Switch family |
| `is_platform_component` | True for an "of which" model |
| `parent_platform_code` | Family code for a component. Empty otherwise |
| `region_code` | `JPN`, `AMR`, `EUR`, `OTH`, `OTH_INCL_EUROPE`, or `GLOBAL` |
| `region_name_verbatim` | Region label printed on the source |
| `is_region_aggregate` | True for `GLOBAL` |
| `game_code` | Slug of a software title. Empty for platform totals and financial lines |
| `game_title` | Title with HTML tags removed and entities decoded |
| `fiscal_year_ending` | Calendar year of March 31. Empty for life-to-date |
| `period_span` | `fiscal_year`, `life_to_date`, `q1`, `q1_q2`, `q1_q3`, or `quarter` |
| `fiscal_quarter` | 1–4 only when `period_span` is `quarter`. Empty for year-to-date and life-to-date |
| `period_label_verbatim` | Header or as-of text the span was taken from |
| `period_start` | Inclusive start. Empty for life-to-date |
| `period_end` | Inclusive end. For life-to-date this is the printed as-of date |
| `as_of_date` | Publication as-of date. It is on or after `period_end` |
| `printed_value` | Number as printed, before scale |
| `scale_token` | `10000` for units of ten thousand, `1000000` for a million of the printed unit, or `millions` for yen |
| `normalized_value` | Printed value times the scale, in units or yen |
| `is_forecast` | False for these historical actuals |
| `is_additive_flow` | True for the flows loaded here. Balance-sheet stocks are not in these files |
| `sales_basis` | `sell_in` for unit rows, `not_applicable` for yen rows |
| `definition_note` | Scale, span, and any page note |
| `sheet_name` | Workbook sheet, or `html` |

`OTH_INCL_EUROPE` is the Other column on sheets that print Japan, the Americas, and Other, with no Europe column. It is not added to the later `OTH` column, which is the residual after Europe is split out.

Rejected-file columns are `source_document_id`, `reason`, `detail`, `period_label`, `platform_name`, `region_name`, and `printed_value`. Reasons include `open_ended_column`, `august_fiscal_year`, `seven_month_stub`, `unmapped_platform`, `unmapped_metric`, `not_a_level`, `duplicate`, and `grain`.

`missing` in the command output counts blank cells under an accepted period header. Those cells are not rows.
