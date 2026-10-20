# Warehouse limitations

The marts describe the disclosures that were loaded. They do not fill gaps.

## Reporting periods that exist

| Population | Span | Fiscal years | Regions |
| --- | --- | --- | --- |
| Unit sell-in, hardware and platform software totals | `fiscal_year` | FY3/1998 through FY3/2026, and only the years a platform was printed | `JPN`, `AMR`, `EUR` or `OTH_INCL_EUROPE`, `OTH`, and `GLOBAL` |
| Unit sell-in, hardware and platform software totals | `life_to_date` | No fiscal year. As-of dates are 2026-03-31 and 2026-06-30 | Worldwide on both documents. Regional life-to-date comes from the March 31 workbook |
| Software titles | `life_to_date` only | No fiscal year | Worldwide. These 36 rows are not in the platform marts |
| Consolidated income | `fiscal_year` | FY3/1991 through FY3/2026, with no missing year in that range | `GLOBAL` only |

A platform's first and last fiscal year follow the printed columns. Switch family hardware runs FY3/2017 through FY3/2026. Switch 2 annual rows exist for FY3/2026 only. Older platforms stop when the sheet stops printing them.

## Comparisons the data does not support

- Life-to-date is not an annual sales figure. The lifetime mart keeps each as-of date. Adding the March 31 workbook total to the June 30 page total recounts the same installed base.
- Some lifetime software and current-generation hardware totals differ between those two as-of dates. Both rows stay. `is_latest_as_of` selects the later page and leaves the earlier workbook row in the table.
- A family total already includes its models. Summing `NSW_FAMILY` with `NSW`, `NSOLED`, or `NSLITE` double-counts. Use `include_in_cross_platform_total` for a cross-platform total, or filter to one component when the question is about that model.
- `GLOBAL` already includes the regions. The regional mart omits `GLOBAL` as a row and repeats it as `disclosed_global_units`.
- Europe is not a stable series. From the sheets that print Europe, the layout is `europe_split`. On earlier sheets, Other includes Europe (`OTH_INCL_EUROPE`). Those codes are never added together.
- FY3/1998 and FY3/1999 for Family Computer / NES, Game Boy, Super NES, and Nintendo 64 do not print an overseas breakdown. Japan and the Americas are present. `reconciliation_status` is `incomplete_breakdown`. The parts are not a worldwide total.
- Where a full regional breakdown exists, the sum of the parts often matches `GLOBAL` exactly. Other groups differ by one printed unit on the ten-thousand scale, and a few differ by more. The mart keeps the disclosed worldwide figure and sets `reconciliation_status` to `within_one_printed_unit` or `differs`. It does not replace either number.
- Negative unit cells are disclosed revisions or returns. They stay in the annual mart. They are not dropped and not replaced with zero.
- Blank workbook cells were not loaded. A missing year is the absence of a row, not a zero.
- Open-ended headers such as a year followed by a tilde were rejected. They are not partial years and not full years.
- The income history starts at FY3/1991. August fiscal years and the seven-month FY3/1990 stub were rejected because this warehouse's fiscal year is April through March. Gross profit, profit before tax, foreign-exchange lines, and printed ratios were not given metric codes.
- Financial amounts are consolidated and worldwide. They cannot be allocated to a platform or to the Americas.
- Software units are a narrower definition than dedicated-platform net sales. Yen rows and unit rows answer different questions.
- Top-selling titles are life-to-date rankings. They are not annual title sales, and they are already inside the platform software total.
- `ref.dim_date` runs from April 1, 1990 through March 31, 2028 so the loaded fiscal years have calendar rows. The dimension still stores no measures.

## Synthetic data

`mart_simulated.weekly_sell_through` is the only mart for the 48 synthetic weekly rows. The reported marts read `raw_official` and require `source_class = 'official_ir'`. A dbt test fails if a `SYN` or `SIM` label appears in a reported analytics mart.
