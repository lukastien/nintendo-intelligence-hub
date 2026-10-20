# Tableau build guide

**Status:** no `.twb`/`.twbx` workbook is shipped. Tableau Public is
installed on the development machine, but publishing requires an
interactive Tableau Public account sign-in, and an unopened workbook
file would be an unverified claim. This guide plus the verified CSV
exports in `data/exports/tableau/` are the deliverable; following the
steps below reproduces the intended workbook in about 20 minutes.

Regenerate the exports any time with:

```bash
python scripts/export_tableau.py
```

Verified row counts: annual 1,968 · trends 691 · regional 1,483 ·
financial 36 · lifetime 175 · metric definitions 10. These are exports
of the genuine official dbt marts — not synthetic data.

## Data sources (one Tableau data source per CSV)

| File | Grain |
| --- | --- |
| `annual_platform_performance.csv` | One platform scope × metric × region × fiscal year (annual flows and life-to-date in separate `observation_type` values) |
| `hardware_software_trends.csv` | Platform × fiscal year hardware/software pairs |
| `regional_performance.csv` | Platform × metric × fiscal year regional splits with disclosed worldwide total |
| `financial_performance.csv` | One consolidated fiscal year |
| `lifetime_platform_sales.csv` | Platform × metric life-to-date snapshots by as-of date |
| `metric_definitions.csv` | Metric code, label, unit, definition, caution |

## Global filters (apply to every sheet)

- `observation_type = annual_flow` for every flow view. Life-to-date
  appears **only** on the lifecycle sheet.
- `include_in_cross_platform_total = TRUE` whenever platforms are
  summed or compared. This is the family/component deduplication rule:
  a family total already includes its component models.
- `region_code = GLOBAL` for worldwide views. Never blend
  `region_layout` values (`europe_split` vs `europe_inside_other`) in
  one regional view.

## Calculated fields

```text
// Operating margin (already in the financial mart as
// operating_margin_calculated; recreate only if rebuilding from lines)
[operating_profit_yen] / [net_sales_yen]

// YoY change (annual flows only)
([value_units] - LOOKUP([value_units], -1)) / ABS(LOOKUP([value_units], -1))

// Hardware attach rate (trends sheet)
[sw_units] / [hw_units]   // guard: set to NULL when [hw_units] = 0

// Regional share of disclosed worldwide
[value_units] / [disclosed_global_units]
```

Guard every division: Tableau returns null on divide-by-zero only if
you wrap it — use `IF [denominator] = 0 THEN NULL ELSE ... END`.
Negative disclosed values are legitimate (returns/revisions); do not
filter them out.

## Sheets

1. **Annual hardware & software performance** — line chart,
   `fiscal_year_ending` on columns, `SUM(value_units)` on rows,
   `metric_code` on colour, filter to one `platform_code`,
   `region_code = GLOBAL`, `observation_type = annual_flow`.
2. **Platform comparison** — bar chart for a selected fiscal year,
   `include_in_cross_platform_total = TRUE`, sorted descending. Add a
   parameter for the fiscal year.
3. **Regional performance** — stacked bars by `region_name` with the
   disclosed worldwide total as a reference line
   (`disclosed_global_units`). Add `reconciliation_status` to the
   tooltip; filter one `region_layout` at a time.
4. **Consolidated financials** — dual axis: bars for
   `net_sales_yen` and `operating_profit_yen`, line for
   `operating_margin_calculated`. Caption: "Consolidated Nintendo
   Co., Ltd., JPY — not Nintendo of America revenue."
5. **Platform lifecycle** — `lifetime_platform_sales.csv` only:
   life-to-date `value_units` by `as_of_date` per platform. Never join
   this sheet's measures to annual flows.
6. **Definitions** — text table from `metric_definitions.csv`.

## Dashboard assembly

One dashboard, 2×2 grid (sheets 1, 3, 4, 5) with sheet 2 as a filter
panel, a fiscal-year parameter, and a footer text box:

> Independent portfolio project. Not affiliated with Nintendo. Figures
> are Nintendo IR disclosures loaded from public investor-relations
> files; see `docs/DATA_SOURCES.md`. Annual flows and life-to-date
> snapshots are never combined.

## Publishing (manual, requires a Tableau Public account)

1. Open Tableau Public → Connect → Text File → `annual_platform_performance.csv`; repeat per file or join on `platform_code`/`fiscal_year_ending` where grains match (do not join lifetime to annual).
2. Build the six sheets above, assemble the dashboard.
3. File → Save to Tableau Public. Publishing makes the workbook public; the underlying data is already public Nintendo IR disclosure, but confirm you are comfortable with that before saving.
4. Record the published URL in README.md's demo section — only after opening the URL in a private window and confirming it loads.
