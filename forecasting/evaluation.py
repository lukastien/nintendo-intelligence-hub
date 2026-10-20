"""Forecast error metrics.

Percentage metrics are guarded: WAPE and sMAPE are only reported when
they are mathematically meaningful. Actuals of zero make percentage
errors undefined, and negative actuals (legitimate disclosed revisions)
make them misleading, so both return ``None`` in those cases instead of
a fabricated number.
"""

from __future__ import annotations

import numpy as np


def _pair(actual: np.ndarray, predicted: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if a.shape != p.shape or a.size == 0:
        raise ValueError("actual and predicted must be non-empty and aligned")
    return a, p


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    a, p = _pair(actual, predicted)
    return float(np.mean(np.abs(p - a)))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    a, p = _pair(actual, predicted)
    return float(np.sqrt(np.mean((p - a) ** 2)))


def bias(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean signed error (prediction minus actual). Positive = over-forecast."""
    a, p = _pair(actual, predicted)
    return float(np.mean(p - a))


def wape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Weighted absolute percentage error, or None when not meaningful."""
    a, p = _pair(actual, predicted)
    denominator = float(np.sum(np.abs(a)))
    if denominator == 0 or np.any(a < 0):
        return None
    return float(np.sum(np.abs(p - a)) / denominator)


def smape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Symmetric MAPE, or None when actuals include negative values."""
    a, p = _pair(actual, predicted)
    if np.any(a < 0):
        return None
    denominator = (np.abs(a) + np.abs(p)) / 2.0
    terms = np.where(denominator == 0, 0.0, np.abs(p - a) / np.where(denominator == 0, 1.0, denominator))
    return float(np.mean(terms))


def summarize(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "bias": bias(actual, predicted),
        "wape": wape(actual, predicted),
        "smape": smape(actual, predicted),
    }
