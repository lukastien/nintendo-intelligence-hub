# Implementation plan

This plan takes the foundation to a portfolio-ready warehouse. Each phase has an exit check. Official numbers enter only in Phase 1, from a reviewed transcription of a public document.

The foundation does not copy figures out of earnings PDFs. A later loader stores `source_value_as_printed`, `source_unit_scale`, and the normalized value, and a check constraint ties those three together.

## Phase 0 — Foundation

Status: delivered in this repository.

- Modular packages for ingestion, transformations, warehouse, dashboards, forecasting, monitoring, configuration, and docs
- Local PostgreSQL via Docker Compose, with BigQuery reserved and failing closed
- Star schema, period-span checks, and dbt views
- Python derivation covered by unit tests, and a rolled-back comparison against the SQL mart
- Synthetic weekly series isolated in `raw_simulated`
- Streamlit shell that shows spans, sources, and metrics
- GitHub Actions workflow for install, `nih init-db`, pytest, and `dbt build`

Exit check: `pytest` passes and `dbt build` passes. `nih init-db` does not insert official measures.

## Public data acquisition

`nih ingest` loads four official IR sources: the dedicated life-to-date unit page, the top-title pages, the regional sales workbook, and the income workbook. Raw bytes and cleaned CSV files are written under gitignored data directories. Quarterly explanatory PDFs and the Euroland unit-sales iframe are not parsed. IGDB and an unbundled licensed file are reported unavailable until credentials or a manifest exist. See [DATA_SOURCES.md](DATA_SOURCES.md).

## Analytics marts

`dbt build` publishes five official marts in `mart_reported`: annual platform performance, hardware and software trends, regional performance, lifetime platform sales, and consolidated financial performance. Each mart keeps the printed grain. Fiscal-year rows stay annual flows. Life-to-date rows stay point-in-time totals and are not summed across as-of dates. The incremental quarter marts stay empty until a file with `q1`, `q1_q2`, or `q1_q3` columns is loaded. Definitions, lineage, example queries, and the quarterly gap are in [BUSINESS_METRICS.md](BUSINESS_METRICS.md), [DATA_LINEAGE.md](DATA_LINEAGE.md), [EXAMPLE_QUERIES.md](EXAMPLE_QUERIES.md), [WAREHOUSE_LIMITATIONS.md](WAREHOUSE_LIMITATIONS.md), and [QUARTERLY_READINESS.md](QUARTERLY_READINESS.md).

## Pipeline orchestration

`python -m nih pipeline run` downloads the configured sources, loads PostgreSQL, audits purity, runs `dbt build`, checks that the marts are queryable, and writes `meta.pipeline_runs`. A repeated run with the same file checksum does not insert another copy of those rows. An unavailable source leaves the previous document in place. Optional IGDB and licensed-file gaps are warnings. The commands, failure modes, and the difference between CI and a durable warehouse are in [PIPELINE_OPERATIONS.md](PIPELINE_OPERATIONS.md), [PIPELINE_ARCHITECTURE.md](PIPELINE_ARCHITECTURE.md), and [DEPLOYMENT.md](DEPLOYMENT.md).

## Phase 1 — One reviewed official document

- Register each explanatory PDF in `meta.source_document` with URL, publication date, SHA-256, and the verbatim column header
- Transcribe one recent earnings document into a review file that a person can check against the PDF
- Map each transcribed column to `period_span` before insert
- Load that file through `DisclosureMeasure`, then into `raw_official`
- Record rejected rows, including life-to-date title totals that someone tried to label as a quarter

Exit check: every loaded amount ties to a document URL and a verbatim header. `dbt build` still passes. A nine-month column is stored as `q1_q3`.

## Phase 2 — History and financial lines

- Load life-to-date hardware and software totals from the dedicated unit-sales page, with the page's as-of date
- Load fiscal-year regional unit sales from the historical transition table, preserving the ten-thousand scale
- Load consolidated income-statement lines and keep balance-sheet stocks marked `additive_flow = false`
- Add stewardship tests for unknown platform codes, aggregate-plus-component collisions, and scale normalization

Exit check: life-to-date rows are absent from the incremental marts. Where Nintendo prints both a year-to-date series and a single quarter, the derived quarter reconciles to the printed quarter or the difference is flagged.

## Business intelligence dashboard

`streamlit run dashboards/app.py` serves five pages over the official marts: Executive Overview, Hardware & Software, Regional Performance, Financial Intelligence, and Pipeline Health. All official figures are read from PostgreSQL with parameterized queries; nothing is hardcoded. Life-to-date snapshots are never summed or charted as annual sales, and component models are excluded from cross-platform totals. Tableau CSV exports come from `python scripts/export_tableau.py`. See [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md), [DASHBOARD_METRICS.md](DASHBOARD_METRICS.md), and [TABLEAU_INTEGRATION.md](TABLEAU_INTEGRATION.md).

## Phase 3 — Reported dashboard

- Add Streamlit pages that read only `mart_reported`
- Subtitle every chart with span, as-of date, sell-in or yen definition, and source document
- Keep the fiscal-span page as the legend for new readers

Exit check: a reviewer can go from a plotted point to the document URL without reading SQL.

## Phase 4 — Simulated monitoring and forecast

The generator, z-score check, and linear baseline already exist so the boundary is tested. This phase expands them.

- Add a longer synthetic weekly series with a known injected spike
- Surface alerts in the app, labeled synthetic, on a page that does not sit next to reported charts
- Compare the linear baseline with a seasonal naive model on the synthetic series
- Add a dbt test that fails if a simulated row is visible to a reported mart

Exit check: the injected spike is flagged, the forecast page states the disclaimer, and the cross-schema test fails when the filter is removed.

## Phase 5 — Optional BigQuery and scheduled refresh

- Add a BigQuery dbt target and a dialect-safe incremental model
- Run the same grain tests against that target
- Schedule `nih` ingestion from GitHub Actions using encrypted secrets
- Keep local PostgreSQL as the default so the project still runs with no cloud account

Exit check: `NIH_WAREHOUSE_TARGET=postgres` remains the documented quickstart, and the cloud run uses the same period spans.

## Risks to carry forward

- PDF tables are easy to mis-read. The verbatim header is stored before the span is assigned.
- Printed scales differ across the historical workbook, the explanatory deck, and the financial statements.
- Later documents revise earlier cumulatives. The derivation keeps the later as-of date and flags the revision.
- Software unit definitions are narrower than dedicated-platform net sales, and edition rules can change. The definition note stays on the row.
- Consolidated regional sales are not a Nintendo of America management P&L. The entity code stays on the financial fact.
