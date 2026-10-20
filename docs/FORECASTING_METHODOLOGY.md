# Forecasting methodology

Forecasting extrapolates **annual fiscal-year flows** from the official
marts. It is deliberately conservative: short annual histories get
simple models, honest backtests, and wide uncertainty — or no forecast
at all.

## Data

| Series | Source | Grain |
| --- | --- | --- |
| Hardware/software units by platform | `mart_annual_platform_performance` | Worldwide, fiscal-year flow, non-component platform scope |
| Consolidated net sales, operating margin | `mart_financial_performance` | Consolidated Nintendo Co., Ltd., fiscal-year flow |

Rules enforced in `forecasting/datasets.py`:

- Life-to-date snapshots never enter a training set.
- Family totals and component models are never combined
  (`include_in_cross_platform_total` scopes only).
- Synthetic weekly rows are rejected (`official_ir` only).
- Missing fiscal years stay missing and are listed per series. They are
  never zero-filled: a platform that did not report did not sell zero.
- A platform series whose reporting ended before the dataset's latest
  fiscal year is classified **retired** and is not forecast. Forecasting
  it would invent a revival.
- A series needs at least 4 annual observations to be forecast at all.
  A launch-year platform (for example, a console in its first reported
  year) is ineligible by rule, not by discretion.

## Models

Baselines (`forecasting/baselines.py`): naive last value, historical
mean, 3-year moving average, drift, linear trend.

Statistical (`forecasting/models.py`, statsmodels): simple exponential
smoothing (≥5 obs), Holt trend (≥6), damped Holt (≥6), ARIMA(1,1,0)
(≥12). A model that fails to converge raises an error that is counted
in `fit_failures`; its predictions are never replaced by another
model's.

## Backtesting and selection

Expanding window, one year ahead. Fold *t* trains on observations from
years strictly before *t*. A fold is scored only when the target year
directly follows the last training year — with a gap year there is no
honest one-year-ahead actual.

Metrics: MAE, RMSE, forecast bias (prediction − actual), WAPE and
sMAPE. WAPE/sMAPE are reported only when meaningful: zero actuals make
them undefined and negative actuals (legitimate disclosed revisions)
make them misleading, so both are stored as null then.

Selection (`forecasting/pipeline.py`):

1. A model needs ≥3 scored folds to be selectable.
2. Lowest backtest RMSE wins, except a simpler model within 10% of the
   best RMSE is preferred (complexity order: naive < mean < moving
   average < drift < trend < SES < Holt < damped Holt < ARIMA).
3. If no model reaches 3 folds, the naive forecast is stored with
   status `limited`; its interval is labelled with its fold support.
4. Selected model, folds, and all metrics are stored per series in
   `forecast.series_evaluations`; every fold is in
   `forecast.backtest_folds`.

## Intervals

80% intervals from backtest residuals: half-width
\(z_{0.9} \cdot \sigma \cdot \sqrt{\text{step}}\), where σ is the selected
model's one-step backtest RMSE (a normal approximation — not empirical
residual quantiles). Stored rows carry `interval_method =
'normal_approx_backtest_rmse'` and `interval_fold_support` (true when
σ came from ≥3 folds). Fold support is not calibration: three
residuals cannot calibrate an interval, and no coverage is
guaranteed. Historical coverage is computed per series from
expanding, leakage-free fold intervals and stored as a diagnostic.
Each forecast also carries a `lifecycle_stage`
(`active` / `end_of_life` / `consolidated`); end-of-life series —
recent values ≤1% of peak — are labelled tail extrapolations, and
retired series remain ineligible.

Documented floors: point forecasts and interval lower bounds for unit
sales and net sales are floored at zero (`point_clipped` /
`interval_clipped` flags) because a large negative sell-in point
forecast is not physically meaningful. Training data is never altered:
small disclosed negative actuals remain exactly as reported. Operating
margin is an unbounded calculated ratio and is never floored.

## Storage and reproducibility

Forecasts live in the `forecast` schema (`warehouse/ddl/070_forecasting.sql`),
never in official facts or `mart_reported`. `python -m nih forecast run`
is independently runnable and reproducible (model version `phase7-v1`);
the dashboard only reads stored runs and never retrains.
