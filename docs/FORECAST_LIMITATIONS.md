# Forecast limitations

These forecasts are a portfolio demonstration of method, not a planning
tool. Read this before quoting any number.

## Structural limitations

- **Console lifecycles dominate.** Launches, price cuts, successor
  announcements, and retirements cause level shifts that univariate
  annual models cannot anticipate. The largest historical errors cluster
  exactly at those breaks.
- **Short series.** Most platform scopes have 10–19 annual observations.
  Statistical power is low, backtest folds are few, and model ranking is
  unstable: one additional year can change the selected model.
- **Retired platforms are excluded, not predicted.** Series ending
  before the latest fiscal year get no forecast. A platform still
  printing near-zero tail values (end-of-life) will receive a forecast
  that mostly extrapolates the tail.
- **New platforms are excluded.** A console with a single reported year
  has no estimable dynamics. Any number produced for it would be
  invented.
- **Annual grain only.** No quarterly seasonality exists in the loaded
  data, so none is modelled. Forecasts are for fiscal years ending
  March 31.
- **No exogenous variables.** Prices, release slates, exchange rates,
  competition, and supply constraints are not inputs. Consolidated
  financial forecasts inherit all of those omissions.
- **Intervals are empirical.** The 80% band comes from backtest
  residuals. It understates uncertainty around structural breaks and is
  flagged uncalibrated when based on fewer than 3 folds.
- **Disclosed values move.** Nintendo restates and revises; a forecast
  trained today is trained on today's vintage of the disclosures.

## What the forecasts are not

- Not Nintendo guidance or company projections of any kind.
- Not Nintendo of America figures: the financial series are
  consolidated Nintendo Co., Ltd. results in yen.
- Not a sum across platforms: family and component scopes are kept
  separate, so platform forecasts must not be added together where a
  family total already includes its models.
- Not evidence about why a result occurred. The models are descriptive
  extrapolations.

## Appropriate use

Compare models, inspect backtest errors, and sanity-check the direction
of a naive extrapolation — with the interval, fold count, and bias
attached. For anything beyond that, the honest answer these tools give
is "insufficient history", and the pipeline is built to say exactly
that.
