"""Forecasting pipeline: backtest, select, forecast, persist.

Selection policy (see docs/FORECASTING_METHODOLOGY.md):

- A series needs at least ``MIN_SERIES_OBSERVATIONS`` annual
  observations to be forecast at all.
- Candidate models are scored by expanding-window backtesting. A model
  needs at least ``MIN_FOLDS_FOR_SELECTION`` scored folds to be
  selectable.
- Among selectable models, the lowest backtest RMSE wins, except that a
  simpler model (lower rank) within ``SIMPLICITY_TOLERANCE`` of the best
  RMSE is preferred.
- If no model reaches the fold minimum, the naive forecast is reported
  with status ``limited`` and an interval with limited fold support. That is a
  transparency label, not a silent fallback to invented numbers: the
  naive value is a real, reproducible calculation.
- Model fit failures are counted and stored, never hidden.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from forecasting import baselines, models
from forecasting.backtesting import ModelBacktest, backtest_model
from forecasting.datasets import AnnualSeries, load_datasets
from forecasting.intervals import interval as make_interval
from forecasting.intervals import residual_sigma
from nih.config import Settings, load_settings

logger = logging.getLogger("nih.forecasting")

MODEL_VERSION = "phase7-v1"
INTERVAL_LEVEL = 0.80
MIN_SERIES_OBSERVATIONS = 4
MIN_FOLDS_FOR_SELECTION = 3
SIMPLICITY_TOLERANCE = 0.10
DEFAULT_HORIZON = 3
ZERO_FLOOR_POINT_METRICS = {"hw_units_sell_in", "sw_units_sell_in", "net_sales_yen"}

MODEL_REGISTRY: list[tuple] = [
    # (name, rank, min_observations, predictor)
    ("naive_last", 0, 1, baselines.naive_last),
    ("historical_mean", 1, 2, baselines.historical_mean),
    ("moving_average_3", 2, 3, baselines.moving_average),
    ("drift", 3, 2, baselines.drift),
    ("linear_trend", 4, 3, baselines.linear_trend),
    ("ses", 5, 5, models.ses),
    ("holt", 6, 6, models.holt),
    ("holt_damped", 7, 6, models.holt_damped),
    ("arima_110", 8, 12, models.arima_110),
]
RANKS = {name: rank for name, rank, _, _ in MODEL_REGISTRY}
PREDICTORS = {name: predictor for name, _, _, predictor in MODEL_REGISTRY}
MIN_OBS = {name: minimum for name, _, minimum, _ in MODEL_REGISTRY}


@dataclass
class SeriesOutcome:
    series: AnnualSeries
    status: str  # 'selected', 'limited', or 'ineligible'
    reason: str = ""
    selected_model: str = ""
    backtests: dict[str, ModelBacktest] = field(default_factory=dict)
    forecasts: list[dict] = field(default_factory=list)
    lifecycle_stage: str = "active"
    interval_coverage: float | None = None
    coverage_folds: int = 0


@dataclass
class ForecastRunResult:
    run_id: str
    status: str
    ok: bool
    exit_code: int
    error_message: str = ""
    series_total: int = 0
    series_forecast: int = 0
    series_limited: int = 0
    series_ineligible: int = 0
    forecasts_written: int = 0
    selected_models: dict[str, int] = field(default_factory=dict)


def evaluate_series(series: AnnualSeries, *, horizon: int = DEFAULT_HORIZON) -> SeriesOutcome:
    """Backtest every eligible model on one series and forecast."""
    if series.ended:
        return SeriesOutcome(
            series=series,
            status="ineligible",
            reason=(
                f"Reporting ended in FY3/{series.last_year}; the platform is "
                "treated as retired. Forecasting it would invent a revival, "
                "so no forecast is produced."
            ),
        )
    if series.observations < MIN_SERIES_OBSERVATIONS:
        return SeriesOutcome(
            series=series,
            status="ineligible",
            reason=(
                f"Only {series.observations} annual observations "
                f"(FY3/{series.first_year}–FY3/{series.last_year}); "
                f"at least {MIN_SERIES_OBSERVATIONS} are required. "
                "Missing years are not treated as zero sales."
            ),
        )
    backtests: dict[str, ModelBacktest] = {}
    for name, _rank, minimum, predictor in MODEL_REGISTRY:
        if series.observations < minimum:
            continue
        backtests[name] = backtest_model(
            series, name, predictor, min_observations=minimum
        )
    selected = _select(backtests)
    values = np.asarray(series.values, dtype=float)
    if selected is None:
        model_name = "naive_last"
        status = "limited"
        reason = (
            f"No model reached {MIN_FOLDS_FOR_SELECTION} scored backtest folds "
            f"(best: {max((len(b.folds) for b in backtests.values()), default=0)}). "
            "Reporting the naive last-value forecast; its interval rests on fewer than 3 folds."
        )
        chosen = backtests.get("naive_last", ModelBacktest("naive_last"))
    else:
        model_name = selected
        status = "selected"
        reason = (
            f"Selected by expanding-window backtest RMSE over "
            f"{len(backtests[selected].folds)} folds; simpler models within "
            f"{int(SIMPLICITY_TOLERANCE * 100)}% of the best RMSE were preferred."
        )
        chosen = backtests[selected]
    predictor = PREDICTORS[model_name]
    try:
        points = np.asarray(predictor(values, horizon), dtype=float)
    except Exception as exc:
        return SeriesOutcome(
            series=series,
            status="ineligible",
            reason=f"Selected model {model_name} failed on the full series: {exc}",
            backtests=backtests,
        )
    residuals = np.array([fold.error for fold in chosen.folds], dtype=float)
    sigma = residual_sigma(residuals, values)
    coverage, coverage_folds = _expanding_coverage(chosen)
    lifecycle = _lifecycle_stage(series)
    metrics = chosen.metrics
    forecasts = []
    for step, point in enumerate(points, start=1):
        point = float(point)
        point_clipped = False
        if series.metric_name in ZERO_FLOOR_POINT_METRICS and point < 0:
            # Documented floor: a large negative sell-in or net-sales point
            # forecast is not physically meaningful. Small disclosed
            # negative actuals stay untouched in the training data.
            point = 0.0
            point_clipped = True
        lower, upper, clipped = make_interval(
            point, sigma, step=step, metric_name=series.metric_name
        )
        forecasts.append(
            {
                "forecast_year": series.last_year + step,
                "horizon_step": step,
                "point_forecast": point,
                "point_clipped": point_clipped,
                "interval_lower": lower,
                "interval_upper": upper,
                "interval_clipped": clipped,
                "interval_fold_support": len(chosen.folds) >= MIN_FOLDS_FOR_SELECTION,
                "lifecycle_stage": lifecycle,
                "selected_model": model_name,
                "backtest_folds": len(chosen.folds),
                "backtest_mae": metrics["mae"],
                "backtest_rmse": metrics["rmse"],
                "backtest_wape": metrics["wape"],
                "backtest_smape": metrics["smape"],
                "backtest_bias": metrics["bias"],
                "status": status,
                "eligibility_note": reason,
            }
        )
    return SeriesOutcome(
        series=series,
        status=status,
        reason=reason,
        selected_model=model_name,
        backtests=backtests,
        forecasts=forecasts,
        lifecycle_stage=lifecycle,
        interval_coverage=coverage,
        coverage_folds=coverage_folds,
    )


def _lifecycle_stage(series: AnnualSeries) -> str:
    """Classify a series for presentation, not for eligibility.

    A still-reporting platform whose last three annual values are at
    most 1% of its historical peak is end-of-life: its forecast is a
    tail extrapolation and must not be presented as an active-platform
    commercial outlook.
    """
    if series.platform == "CONSOLIDATED":
        return "consolidated"
    values = np.asarray(series.values, dtype=float)
    if values.size >= 3 and float(np.max(values)) > 0:
        if float(np.max(values[-3:])) <= 0.01 * float(np.max(values)):
            return "end_of_life"
    return "active"


def _expanding_coverage(chosen: ModelBacktest) -> tuple[float | None, int]:
    """Historical interval coverage without temporal leakage.

    Each fold's interval is built only from residuals of earlier folds
    of the same model, so a fold never contributes to its own interval.
    Returns (coverage, scored folds); coverage is None below 3 folds.
    """
    folds = chosen.folds
    hits = 0
    scored = 0
    prior_errors: list[float] = []
    for fold in folds:
        if len(prior_errors) >= 2:
            sigma = float(np.sqrt(np.mean(np.square(prior_errors))))
            lower = fold.prediction - 1.2816 * sigma
            upper = fold.prediction + 1.2816 * sigma
            scored += 1
            if lower <= fold.actual <= upper:
                hits += 1
        prior_errors.append(fold.error)
    if scored < 3:
        return None, scored
    return hits / scored, scored


def _select(backtests: dict[str, ModelBacktest]) -> str | None:
    candidates = [
        (name, result)
        for name, result in backtests.items()
        if len(result.folds) >= MIN_FOLDS_FOR_SELECTION and result.metrics["rmse"] is not None
    ]
    if not candidates:
        return None
    best_rmse = min(result.metrics["rmse"] for _, result in candidates)
    within = [
        name for name, result in candidates
        if result.metrics["rmse"] <= best_rmse * (1 + SIMPLICITY_TOLERANCE)
    ]
    return min(within, key=lambda name: RANKS[name])


def ensure_forecast_tables(connection) -> None:
    """Create the forecast schema from the shared DDL when missing."""
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('forecast.forecasts')")
        if cursor.fetchone()[0] is not None:
            return
    from warehouse.apply import split_sql

    ddl = Path(__file__).resolve().parents[1] / "warehouse" / "ddl" / "070_forecasting.sql"
    with connection.cursor() as cursor:
        for statement in split_sql(ddl.read_text(encoding="utf-8")):
            cursor.execute(statement)
    connection.commit()


def run_forecast(
    *,
    horizon: int = DEFAULT_HORIZON,
    settings: Settings | None = None,
    series_list: list[AnnualSeries] | None = None,
) -> ForecastRunResult:
    """Evaluate all series, persist forecasts, and return a summary."""
    from nih.db import connect

    settings = settings or load_settings()
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    try:
        series_list = series_list if series_list is not None else load_datasets(settings)
        outcomes = [evaluate_series(item, horizon=horizon) for item in series_list]
    except Exception as exc:
        logger.exception("forecast dataset preparation failed")
        return ForecastRunResult(run_id, "failed", False, 1, str(exc))
    selected_models: dict[str, int] = {}
    written = 0
    try:
        with connect(settings) as connection:
            ensure_forecast_tables(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into forecast.forecast_runs
                        (run_id, started_at, status, model_version, horizon_years, series_total)
                    values (%s, %s, 'running', %s, %s, %s)
                    """,
                    (run_id, started, MODEL_VERSION, horizon, len(outcomes)),
                )
            connection.commit()
            for outcome in outcomes:
                _persist_outcome(connection, run_id, outcome)
                if outcome.status in ("selected", "limited"):
                    selected_models[outcome.selected_model] = (
                        selected_models.get(outcome.selected_model, 0) + 1
                    )
                    written += len(outcome.forecasts)
            forecast_count = sum(1 for o in outcomes if o.status == "selected")
            limited_count = sum(1 for o in outcomes if o.status == "limited")
            ineligible_count = sum(1 for o in outcomes if o.status == "ineligible")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update forecast.forecast_runs
                    set finished_at = %s, status = 'succeeded',
                        series_forecast = %s, series_limited = %s,
                        series_ineligible = %s, forecasts_written = %s
                    where run_id = %s
                    """,
                    (
                        datetime.now(timezone.utc),
                        forecast_count,
                        limited_count,
                        ineligible_count,
                        written,
                        run_id,
                    ),
                )
            connection.commit()
    except Exception as exc:
        logger.exception("forecast persistence failed")
        return ForecastRunResult(run_id, "failed", False, 1, str(exc))
    return ForecastRunResult(
        run_id=run_id,
        status="succeeded",
        ok=True,
        exit_code=0,
        series_total=len(outcomes),
        series_forecast=forecast_count,
        series_limited=limited_count,
        series_ineligible=ineligible_count,
        forecasts_written=written,
        selected_models=selected_models,
    )


def _persist_outcome(connection, run_id: str, outcome: SeriesOutcome) -> None:
    series = outcome.series
    with connection.cursor() as cursor:
        for name, result in outcome.backtests.items():
            metrics = result.metrics
            cursor.execute(
                """
                insert into forecast.series_evaluations
                    (run_id, series_key, metric_name, platform, model_name,
                     train_observations, backtest_folds, mae, rmse, wape, smape, bias,
                     selected, fit_failures, interval_coverage, coverage_folds)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (run_id, series_key, model_name) do nothing
                """,
                (
                    run_id, series.series_key, series.metric_name, series.platform, name,
                    series.observations, len(result.folds), metrics["mae"], metrics["rmse"],
                    metrics["wape"], metrics["smape"], metrics["bias"],
                    name == outcome.selected_model and outcome.status == "selected",
                    len(result.failures),
                    outcome.interval_coverage if name == outcome.selected_model else None,
                    outcome.coverage_folds if name == outcome.selected_model else 0,
                ),
            )
            for fold in result.folds:
                cursor.execute(
                    """
                    insert into forecast.backtest_folds
                        (run_id, series_key, model_name, target_year,
                         train_observations, prediction, actual, error)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (run_id, series_key, model_name, target_year) do nothing
                    """,
                    (
                        run_id, series.series_key, name, fold.target_year,
                        fold.train_observations, fold.prediction, fold.actual, fold.error,
                    ),
                )
        for forecast in outcome.forecasts:
            cursor.execute(
                """
                insert into forecast.forecasts
                    (run_id, series_key, metric_name, platform, platform_name,
                     train_start_year, train_end_year, train_observations,
                     forecast_year, horizon_step, point_forecast, point_clipped,
                     interval_lower, interval_upper, interval_level, interval_clipped,
                     interval_fold_support, lifecycle_stage, selected_model, backtest_folds,
                     backtest_mae, backtest_rmse, backtest_wape, backtest_smape,
                     backtest_bias, status, eligibility_note, data_provenance, model_version)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (run_id, series_key, forecast_year) do nothing
                """,
                (
                    run_id, series.series_key, series.metric_name, series.platform,
                    series.platform_name, series.first_year, series.last_year,
                    series.observations, forecast["forecast_year"], forecast["horizon_step"],
                    forecast["point_forecast"], forecast["point_clipped"], forecast["interval_lower"],
                    forecast["interval_upper"], INTERVAL_LEVEL, forecast["interval_clipped"],
                    forecast["interval_fold_support"], forecast["lifecycle_stage"], forecast["selected_model"],
                    forecast["backtest_folds"], forecast["backtest_mae"],
                    forecast["backtest_rmse"], forecast["backtest_wape"],
                    forecast["backtest_smape"], forecast["backtest_bias"],
                    forecast["status"], forecast["eligibility_note"],
                    series.provenance, MODEL_VERSION,
                ),
            )
    connection.commit()


def forecast_status(settings: Settings | None = None) -> dict:
    from nih.db import connect

    settings = settings or load_settings()
    with connect(settings) as connection:
        ensure_forecast_tables(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select run_id, started_at, status, series_total, series_forecast,
                       series_limited, series_ineligible, forecasts_written, model_version
                from forecast.forecast_runs
                order by started_at desc
                limit 1
                """
            )
            latest = cursor.fetchone()
            cursor.execute(
                """
                select selected_model, count(distinct series_key)
                from forecast.forecasts
                where run_id = (select run_id from forecast.forecast_runs order by started_at desc limit 1)
                group by selected_model
                order by selected_model
                """
            )
            models = cursor.fetchall()
    return {"latest": latest, "models": models}


def forecast_history(limit: int = 10, settings: Settings | None = None) -> list[tuple]:
    from nih.db import connect

    settings = settings or load_settings()
    with connect(settings) as connection:
        ensure_forecast_tables(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select run_id, started_at, status, series_total, series_forecast,
                       series_limited, series_ineligible, forecasts_written
                from forecast.forecast_runs
                order by started_at desc
                limit %s
                """,
                (int(limit),),
            )
            return cursor.fetchall()
