# Dashboard guide

Launch:

```bash
docker compose up -d --wait
nih init-db
python -m nih pipeline run
streamlit run dashboards/app.py
```

Open the URL Streamlit prints. The sidebar shows whether PostgreSQL is connected and the most recent successful pipeline finish. If PostgreSQL is unavailable, the app stops with instructions and shows no substitute figures.

No business figure is hardcoded. Every official number is read, with parameterized SQL, from the dbt marts in PostgreSQL. Queries are cached for five minutes (pipeline data for two minutes). Use Streamlit's rerun or restart the app after a pipeline run if you need the newest data immediately.

## Pages

| Page | What it answers | Source mart |
| --- | --- | --- |
| Executive Overview | Worldwide annual hardware and software sell-in for one fiscal year, a comparable year-over-year change when the platform set is unchanged, consolidated net sales, operating profit, and trends | `mart_annual_platform_performance`, `mart_financial_performance` |
| Hardware & Software | Annual hardware and software flows for one platform scope, the software-per-hardware ratio, a cross-platform comparison, and life-to-date snapshots | `mart_hardware_software_trends`, `mart_lifetime_platform_sales` |
| Regional Performance | Regional annual sell-in under one region definition, with share of the disclosed worldwide total where the breakdown is complete | `mart_regional_performance` |
| Financial Intelligence | Consolidated annual net sales, operating profit, ordinary profit, profit attributable to owners, calculated margins, and growth | `mart_financial_performance` |
| Pipeline Health | Latest and historical pipeline runs, record counts, official source freshness, optional-source warnings, and dataset separation | `meta.pipeline_runs` and the fact tables |

## Filters worth understanding

- A family total such as the Switch family already includes its models. The executive total and comparison exclude component models through `include_in_cross_platform_total`.
- Worldwide (`GLOBAL`) is never added to the regional rows.
- Europe-split (Japan, Americas, Europe, Other) and Europe-inside-Other (Japan, Americas, Other including Europe) are selected as separate region definitions. They are never combined.
- Life-to-date snapshots are charted by as-of date. They are not summed and are not annual sales. Switch 2 life-to-date snapshots are a single recent platform history, not a long annual series.
- A comparable year-over-year total appears only when the same non-component platform scopes reported in both years. A platform launch or retirement leaves the growth blank.
- Ratios and margins are blank when the denominator is zero or a value is missing.

The fiscal-span reference chart still exists in `dashboards/spans.py` and its tests. It explains why a nine-month cumulative window is not the third fiscal quarter.

## Synthetic data

The 48 synthetic weekly rows are counted on Pipeline Health to show that they remain isolated. They are not charted on any official page, and dbt tests fail if a synthetic label appears in an official mart.
