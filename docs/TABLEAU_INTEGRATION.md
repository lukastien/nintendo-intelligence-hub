# Tableau integration

No Tableau workbook was built in this phase. What exists is a clean export and a documented connection, so a Tableau dashboard can be built without re-deriving the warehouse rules.

## Export the marts

```bash
docker compose up -d --wait
python -m nih pipeline run
python scripts/export_tableau.py
```

Files are written to `data/exports/tableau/` (gitignored):

| File | Mart | Grain |
| --- | --- | --- |
| `annual_platform_performance.csv` | `mart_annual_platform_performance` | One fiscal-year sell-in flow per metric, platform scope, and region |
| `hardware_software_trends.csv` | `mart_hardware_software_trends` | One fiscal year, non-component platform, and region |
| `regional_performance.csv` | `mart_regional_performance` | One fiscal-year regional flow (no worldwide row) |
| `financial_performance.csv` | `mart_financial_performance` | One consolidated fiscal year |
| `lifetime_platform_sales.csv` | `mart_lifetime_platform_sales` | One life-to-date snapshot per document and as-of date |
| `metric_definitions.csv` | `dashboards/definitions.py` | One metric definition |

Columns keep the mart names (`fiscal_year_ending`, `platform_code`, `region_code`, `value_units`, `source_document_id`, `source_url`, `content_sha256`, `as_of_date`). `observation_type` separates `annual_flow` from `point_in_time_cumulative`. Do not rename `value_units` to sales without keeping the metric and observation type beside it.

## Connect Tableau to PostgreSQL instead

A live connection keeps the same guarantees as the export:

1. In Tableau Desktop, connect to PostgreSQL.
2. Server `localhost`, port `54329`, database `nintendo_intel`, user `nih`. The password is the local value from your `.env`; do not publish it in a workbook.
3. Use schema `mart_reported` and the five views above. Do not connect Tableau to `raw_official` for a published dashboard, and never union `raw_simulated` into an official view.
4. For a shared or cloud warehouse, point the connection at that PostgreSQL host instead. This project has not provisioned one.

## Suggested Tableau layout (mirrors the Streamlit pages)

1. **Executive** — KPI band for one fiscal year (worldwide hardware, worldwide software, consolidated net sales, operating profit and calculated margin), annual hardware/software trend lines, and a platform bar for that year. Filter on `include_in_cross_platform_total = true`.
2. **Platform** — hardware and software bars by fiscal year for one platform, the software-per-hardware ratio below, and life-to-date snapshots on a separate sheet filtered to `period_span = life_to_date`.
3. **Regional** — regional bars under a single `region_layout` parameter. Show `regional share` only where `reconciliation_status` is not incomplete, and keep `GLOBAL` out of the rows.
4. **Financial** — net sales and profit lines in JPY, calculated margin lines, and a growth table.
5. **Pipeline** — from `meta.pipeline_runs`, run status, durations, and extracted/inserted/updated/unchanged/rejected counts.

Calculated fields in Tableau should reproduce the definitions in `docs/DASHBOARD_METRICS.md`, in particular: exclude component models from cross-platform totals, and leave a ratio blank when its denominator is zero.

## Verification boundary

The CSV export and this connection guide were produced and checked from this repository. A Tableau workbook was not created, and no Tableau rendering was tested.
