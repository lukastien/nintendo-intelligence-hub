"""Statistical forecasters (statsmodels) behind a common interface.

Each model declares the minimum number of training observations it
needs. Models that fail to converge raise :class:`ModelFitError`; the
caller records the failure instead of substituting another model's
numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class ModelFitError(RuntimeError):
    """A model could not be fit or produced non-finite forecasts."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    rank: int  # Simplicity order for tie-breaking; lower is simpler.
    min_observations: int
    kind: str  # 'baseline' or 'statistical'


def _finite(values: np.ndarray, name: str) -> np.ndarray:
    result = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(result)):
        raise ModelFitError(f"{name} produced non-finite forecasts")
    return result


def _smoothing(train: np.ndarray, horizon: int, *, trend, damped: bool, name: str) -> np.ndarray:
    import warnings

    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    values = np.asarray(train, dtype=float)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(
                values,
                trend=trend,
                damped_trend=damped,
                initialization_method="estimated",
            ).fit(optimized=True)
            forecast = np.asarray(fit.forecast(horizon), dtype=float)
    except Exception as exc:
        raise ModelFitError(f"{name} failed to converge: {exc}") from exc
    return _finite(forecast, name)


def ses(train: np.ndarray, horizon: int) -> np.ndarray:
    return _smoothing(train, horizon, trend=None, damped=False, name="ses")


def holt(train: np.ndarray, horizon: int) -> np.ndarray:
    return _smoothing(train, horizon, trend="add", damped=False, name="holt")


def holt_damped(train: np.ndarray, horizon: int) -> np.ndarray:
    return _smoothing(train, horizon, trend="add", damped=True, name="holt_damped")


def arima_110(train: np.ndarray, horizon: int) -> np.ndarray:
    """ARIMA(1,1,0): one autoregressive term on first differences."""
    import warnings

    from statsmodels.tsa.arima.model import ARIMA

    values = np.asarray(train, dtype=float)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ARIMA(values, order=(1, 1, 0)).fit()
            forecast = np.asarray(fit.forecast(steps=horizon), dtype=float)
    except Exception as exc:
        raise ModelFitError(f"arima_110 failed to converge: {exc}") from exc
    return _finite(forecast, "arima_110")
