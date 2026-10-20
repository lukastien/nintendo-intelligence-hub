# Portfolio case study: Nintendo Intelligence Hub

## 1. Business problem

A business intelligence analyst at a company like Nintendo of America
needs trustworthy platform, regional, and financial performance
numbers. The source material — Nintendo's public investor-relations
disclosures — is authoritative but hostile to casual analysis: decades
of consoles, changing regional definitions, cumulative reporting
spans, and platform families whose totals already contain their
component models. The failure mode is silent: a spreadsheet that
double-counts Switch Lite inside the Switch family, or reads an
April–December cumulative column as "Q3", produces confident, wrong
answers.

## 2. Why it matters

These are the exact errors BI teams ship in dashboards. The project
treats correctness of grain and provenance as the product: every mart
row can be traced to a source document, every total states what it
includes, and every derived number carries the rule that produced it.

## 3. Data sources

Genuine Nintendo IR material only: the dedicated hardware/software
unit-sales page, top-selling title pages, and the historical
regional-sales and consolidated-income workbooks. 2,179 unit-sales
facts and 144 financial facts (FY3/1991–FY3/2026). A small synthetic
weekly dataset exists to demonstrate isolation discipline; it is
stored in a separate schema and barred from official marts by dbt
tests. Sources that cannot be retrieved are reported unavailable —
never substituted.

## 4. ETL and warehouse architecture

Python ingestion (per-document, transactional, checksum-idempotent)
loads `raw_official`; dbt builds five marts in `mart_reported`
(annual platform performance, regional performance, hardware/software
trends, lifetime snapshots, financial performance). The orchestrator
(`nih pipeline run`) sequences ingest → audit → dbt → monitoring under
an advisory lock, records every run, and makes reruns no-ops
(verified: 2,323 records unchanged). Fiscal logic is implemented once
in Python and mirrored in SQL: Nintendo's year ends March 31, Q1–Q3
columns are cumulative, and quarters are derived only from adjacent
year-to-date spans.

## 5. BI metrics and dashboards

Six Streamlit pages read the marts at runtime. Definitions are
enforced structurally: family/component double-counting is prevented
by `include_in_cross_platform_total`, life-to-date is never mixed with
annual flows, regional layouts are never combined, ratios go blank on
zero denominators, and consolidated financials are labelled as
Nintendo Co., Ltd. group results — not Nintendo of America revenue.

## 6. Monitoring and anomaly detection

A monitoring layer evaluates pipeline health, data quality (duplicate
grains, schema drift, missing documents, reconciliation deviations),
freshness against publication schedules, and annual business movements
(YoY and MAD-based robust scores). Alerts are fingerprint-deduplicated
with an audited lifecycle. Crucially, known legitimate conditions —
negative disclosed revisions, incomplete 1990s regional breakdowns,
family/component coexistence — are excluded by construction. A live
evaluation flags exactly the four regional reconciliations that exceed
documented thresholds and resolves its own stale failure alert once
the pipeline is healthy again.

## 7. Forecasting and evaluation

Nine models (naive through ARIMA(1,1,0)) are compared by
expanding-window backtesting: 980 scored folds, training strictly
before each target year. Selection prefers simpler models within 10%
of the best RMSE — on the consolidated series, the naive forecast
honestly wins. Retired platforms (16 series) and the launch-year
Switch 2 series are excluded by rule rather than forecast with
invented confidence. Intervals are a normal approximation over
backtest RMSE, labelled as such; leakage-free historical coverage
(63% on consolidated net sales against an 80% nominal band) is
reported instead of a calibration claim.

## 8. Engineering challenges and solutions

- **Cumulative spans masquerading as quarters** → span-aware period
  model in Python and SQL; quarterly marts are empty because no
  quarterly source columns are loaded, and the dashboard says so.
- **Workbook scale and layout drift across decades** → per-source
  parsers with rejection accounting (129 rejected cells, all
  explained), printed-scale-aware reconciliation thresholds.
- **Test pollution of live state** → isolated FY2099-style fixtures,
  per-document loads, and monitoring that heals stale alerts.
- **Phase 8 review catch** → intervals had been labelled "calibrated"
  on ≥3 folds. Renamed to fold support, lifecycle stages added
  (active vs end-of-life tail extrapolations), and honest coverage
  computed.

## 9. Measurable outcomes

- 2,323 genuine records loaded; rerun = 0 inserted, 0 updated.
- 100 Python tests passing; 72 dbt results, 0 failures.
- Monitoring: 165 active findings, second run creates 0 duplicates.
- Forecasting: 8 of 26 series forecast; 18 excluded with stated reasons.
- Read-only demo role proven: writes and raw-schema access blocked.

## 10. Limitations and future work

Annual series are short and lifecycle-dominated, so forecasts are
baseline extrapolations, not predictions; intervals understate
structural-break risk. Quarterly PDFs are not parsed. The public demo
awaits the owner's cloud accounts (checklist prepared). Future work:
quarterly disclosure parsing when a defensible source exists, forecast
reconciliation across platform scopes, and scheduled monitoring
notifications.

*Independent portfolio project. Nintendo did not request, use, or
endorse this work.*
