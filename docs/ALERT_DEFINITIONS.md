# Alert definitions

Severity means: **critical** is a pipeline or mandatory data-integrity
failure, **warning** is a meaningful data-quality discrepancy, and
**info** is an unusual but potentially legitimate business movement.

## Operational

| Alert type | Severity | Rule |
| --- | --- | --- |
| `pipeline_failure` | critical | The latest finished pipeline run is `failed`, or a run failed before the monitoring stage and was recorded by the orchestrator |
| `pipeline_never_run` | warning | No row exists in `meta.pipeline_runs` |
| `missing_source_document` | critical | A mandatory document family (`nintendo_dedicated_units`, `nintendo_sales_transition`, `nintendo_income_transition`, `nintendo_top_titles`) is absent from `meta.source_document` |
| `source_freshness_overdue` | warning | The newest as-of date in a publication group is older than its window: the March 31 annual close plus 90 days, or the latest fiscal quarter-end at least 45 days old for quarterly IR pages |

## Data quality

| Alert type | Severity | Rule |
| --- | --- | --- |
| `duplicate_official_grain` | critical | Two rows share the fact grain key (document, metric, platform, region, title, fiscal year, span, quarter) |
| `missing_mandatory_field` | critical | A unit row has no metric, platform, or region code |
| `missing_measure_value` | warning | A stored unit row has no normalized value (blank source cells are normally not loaded at all) |
| `invalid_reporting_period` | critical | A row fails `ref.period_bounds_ok` for its fiscal year and span |
| `synthetic_official_mixing` | critical | An official fact is not `official_ir`, a financial row is not the consolidated entity, or a simulated row is not labelled synthetic |
| `mart_unavailable` | critical | A required official mart cannot be queried or is empty while facts are loaded |
| `source_schema_change` | critical / warning | Expected columns are missing from `raw_official` (critical) or unexpected columns appeared (warning) |
| `source_row_count_change` | warning | A document's row count moved at least 20% **and** at least 10 rows versus the previous successful evaluation. The first evaluation only records the baseline |
| `regional_reconciliation_deviation` | warning | A complete regional breakdown marked `differs` deviates by more than 10,000 units **and** more than 0.1% from the disclosed worldwide total |

## Business (all informational)

Only annual flows are evaluated, worldwide, inside one non-component
platform scope, one metric, and consecutive fiscal years. Life-to-date
rows are filtered out by the mart and again by the detector.

| Alert type | Rule |
| --- | --- |
| `yoy_business_movement` | Absolute year-over-year change of at least 50% (`NIH_MONITOR_YOY_CHANGE`) |
| `robust_business_movement` | At least five prior annual observations, a median/MAD robust z-score of at least 3.5 (`NIH_MONITOR_ROBUST_Z`), and the same 50% YoY gate |
| `financial_business_movement` | Consolidated net sales or operating profit moves at least 50% year over year |
| `margin_business_movement` | Calculated operating margin moves at least 5 percentage points (`NIH_MONITOR_MARGIN_CHANGE_POINTS`) |

Every business explanation names the metric, both fiscal years, the
percentage or point change, and the rule. When a platform scope has two
or fewer reported years, the explanation says a launch or early-lifecycle
ramp is a plausible legitimate explanation.

## Known conditions that are not alerts

- Negative annual unit values (disclosed returns or revisions) stay in
  the data and are not defects. They can appear as an observed value in a
  business movement, like any other reported figure.
- Regional differences within one printed unit, and the `differs` rows
  under the thresholds above, are reporting precision.
- `incomplete_breakdown` years (the older sheets without an overseas
  split) are excluded from the regional rule entirely.
- Family totals and component models coexisting is the correct source
  structure. The marts prevent summing them; monitoring does not flag
  their coexistence.
- Europe-split and Europe-inside-Other rows are never combined by a rule.
- A gap year produces no year-over-year comparison, and a zero or missing
  prior value is never treated as a denominator.

## Limitations

- Robust scores need at least five prior observations and non-zero MAD;
  sparse or flat histories get no statistical score.
- A year-over-year flag on a long-lived platform can reflect a launch of
  a successor, a retirement, or a genuine demand change. Monitoring
  cannot distinguish those; it only asks for investigation.
- Row-count baselines come from the previous successful evaluation, so
  the first run after this feature lands cannot flag a count change.
- No quarterly anomaly exists, because no quarterly source columns are
  loaded.
