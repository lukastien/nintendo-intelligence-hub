"""Prediction intervals from historical backtest residuals.

Method: the interval half-width is ``z * sigma * sqrt(step)`` where
``sigma`` is the RMSE of the selected model's one-step backtest
residuals and ``z`` is the normal quantile for the stated level. This is
an empirical residual interval. With few folds it is **not** a
calibrated statistical interval and must not be read as a guarantee of
coverage; the forecast rows record how many folds the width came from.

Clipping: the lower bound is clipped at zero only for consolidated net
sales (``net_sales_yen``), where a negative interval bound has no
physical meaning. Unit-sales series keep negative bounds because
Nintendo has disclosed negative annual values (returns/revisions), and
operating margin is an unbounded calculated ratio. Every clip is
flagged on the stored row.
"""

from __future__ import annotations

import numpy as np

Z_80 = 1.2816
ZERO_FLOOR_METRICS = {"net_sales_yen"}


def residual_sigma(residuals: np.ndarray, fallback_values: np.ndarray) -> float:
    """RMSE of backtest residuals, falling back to first differences."""
    values = np.asarray(residuals, dtype=float)
    if values.size >= 2:
        return float(np.sqrt(np.mean(values**2)))
    series = np.asarray(fallback_values, dtype=float)
    if series.size >= 3:
        return float(np.std(np.diff(series), ddof=1))
    return 0.0


def interval(
    point: float,
    sigma: float,
    *,
    step: int = 1,
    metric_name: str = "",
) -> tuple[float, float, bool]:
    """Return (lower, upper, clipped) for an 80% residual interval."""
    half = Z_80 * sigma * np.sqrt(step)
    lower = point - half
    upper = point + half
    clipped = False
    if metric_name in ZERO_FLOOR_METRICS and lower < 0:
        lower = 0.0
        clipped = True
    return float(lower), float(upper), clipped
