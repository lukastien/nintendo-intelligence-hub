"""Expanding-window backtesting with strict temporal separation.

For each candidate target year, the training window contains only
observations from earlier fiscal years. A fold is only scored when the
target year is exactly one year after the last training year: with a
gap year there is no honest one-year-ahead actual to compare against,
and the fold is skipped rather than scored against a later year.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from forecasting.datasets import AnnualSeries
from forecasting.evaluation import summarize

MIN_TRAIN_OBSERVATIONS = 4


@dataclass
class Fold:
    model_name: str
    target_year: int
    train_observations: int
    prediction: float
    actual: float

    @property
    def error(self) -> float:
        return self.prediction - self.actual


@dataclass
class ModelBacktest:
    model_name: str
    folds: list[Fold] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def metrics(self) -> dict[str, float | None]:
        if not self.folds:
            return {"mae": None, "rmse": None, "bias": None, "wape": None, "smape": None}
        actual = np.array([f.actual for f in self.folds])
        predicted = np.array([f.prediction for f in self.folds])
        return summarize(actual, predicted)


def backtest_model(
    series: AnnualSeries,
    model_name: str,
    predict,
    *,
    min_train: int = MIN_TRAIN_OBSERVATIONS,
    min_observations: int = 1,
) -> ModelBacktest:
    """Score one model over every scorable expanding-window fold."""
    result = ModelBacktest(model_name=model_name)
    values = np.asarray(series.values, dtype=float)
    years = series.years
    for index in range(len(values)):
        if index < max(min_train, min_observations):
            continue
        if years[index] != years[index - 1] + 1:
            continue  # Gap year: no one-year-ahead actual exists.
        train = values[:index]
        try:
            prediction = float(np.asarray(predict(train, 1), dtype=float)[0])
        except Exception as exc:
            result.failures.append(f"FY3/{years[index]}: {exc}")
            continue
        if not np.isfinite(prediction):
            result.failures.append(f"FY3/{years[index]}: non-finite forecast")
            continue
        result.folds.append(
            Fold(
                model_name=model_name,
                target_year=years[index],
                train_observations=index,
                prediction=prediction,
                actual=float(values[index]),
            )
        )
    return result
