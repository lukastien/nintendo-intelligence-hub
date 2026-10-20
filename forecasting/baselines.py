"""Transparent baseline forecasters.

Every baseline takes the training values in fiscal-year order and a
horizon in years, and returns one point forecast per horizon step.
Baselines are the benchmark every statistical model must beat in
backtesting; they are not strawmen.
"""

from __future__ import annotations

import numpy as np


def _values(train: np.ndarray) -> np.ndarray:
    values = np.asarray(train, dtype=float)
    if values.size == 0:
        raise ValueError("a forecaster needs at least one training observation")
    return values


def naive_last(train: np.ndarray, horizon: int) -> np.ndarray:
    """Repeat the last observed value."""
    values = _values(train)
    return np.full(horizon, values[-1])


def historical_mean(train: np.ndarray, horizon: int) -> np.ndarray:
    values = _values(train)
    return np.full(horizon, float(values.mean()))


def moving_average(train: np.ndarray, horizon: int, window: int = 3) -> np.ndarray:
    """Mean of the last `window` observations, repeated across the horizon."""
    values = _values(train)
    tail = values[-min(window, values.size):]
    return np.full(horizon, float(tail.mean()))


def drift(train: np.ndarray, horizon: int) -> np.ndarray:
    """Last value plus the average historical change per step (Gibrat drift)."""
    values = _values(train)
    if values.size < 2:
        return np.full(horizon, values[-1])
    slope = (values[-1] - values[0]) / (values.size - 1)
    steps = np.arange(1, horizon + 1, dtype=float)
    return values[-1] + slope * steps


def linear_trend(train: np.ndarray, horizon: int) -> np.ndarray:
    """Ordinary least squares on the observation index, extrapolated."""
    values = _values(train)
    if values.size < 2:
        return np.full(horizon, values[-1])
    index = np.arange(values.size, dtype=float)
    design = np.column_stack([np.ones_like(index), index])
    coef, *_ = np.linalg.lstsq(design, values, rcond=None)
    future = np.arange(values.size, values.size + horizon, dtype=float)
    return coef[0] + coef[1] * future
