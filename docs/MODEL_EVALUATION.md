# Model evaluation

Evaluation happens on historical one-year-ahead forecasts, never on
in-sample fit. Every number below is reproducible from
`forecast.backtest_folds` for the latest run.

## How to read the comparison table

For each series the dashboard and `forecast.series_evaluations` show one
row per candidate model: scored folds, MAE, RMSE, WAPE, sMAPE, bias,
fit failures, and the selected flag.

- **Folds first.** A low RMSE over 2 folds is weaker evidence than a
  slightly higher RMSE over 15 folds. Selection requires ≥3 folds.
- **Bias sign.** Positive bias means the model systematically
  over-forecast; negative means under-forecast. Bias near zero with a
  large RMSE means errors cancel, not that forecasts are accurate.
- **Blank WAPE/sMAPE.** The actuals include zero or negative values, so
  a percentage error would be undefined or misleading. MAE/RMSE still
  apply.
- **Fit failures.** Counted, not hidden. ARIMA on a short or flat series
  failing to converge is information, not a defect to paper over.

## Why simple models often win here

Annual platform series are 10–36 observations long and are dominated by
console lifecycles: launch ramps, peaks, successor cannibalisation, and
retirement cliffs. No univariate method models those breaks. On such
series the naive and drift baselines are genuinely competitive, which is
why selection prefers a simpler model within 10% of the best RMSE and
why the methodology forbids declaring a winner from a single fold.

## Coverage

The 80% interval is an empirical residual interval. Historical coverage
can be computed per series from stored folds (share of actuals inside
the would-be interval), but with the fold counts available here it is a
diagnostic, not a calibration claim. The stored `interval_fold_support` flag marks series whose σ rests
on at least 3 folds; it is explicitly not a calibration claim.
Leakage-free historical coverage (each fold's interval built only
from earlier folds) is stored per selected model as a diagnostic.

## Worked interpretation

A selected ARIMA on a long consolidated series means: among models with
enough scored folds, its one-year-ahead errors were smallest, and no
simpler model was within 10%. It does not mean the business follows an
ARIMA process, and the forecast should be quoted with its interval,
fold count, and bias — or not quoted at all.
