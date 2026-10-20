"""Phase 7 forecasting tests.

All series use invented FY2090s values and SYN platform codes. They test
forecasting arithmetic and eligibility rules only; no published figure
appears here. PostgreSQL persistence tests use an isolated synthetic
series list passed directly to the pipeline and are cleaned up by run.
"""

import numpy as np
import pandas as pd
import pytest

from forecasting import baselines, evaluation
from forecasting.backtesting import backtest_model
from forecasting.datasets import AnnualSeries, build_series
from forecasting.intervals import interval, residual_sigma
from forecasting.pipeline import evaluate_series
from warehouse.audit import database_reachable


def _series(values, *, years=None, platform="SYN_A", metric="hw_units_sell_in", ended=False):
    years = years or tuple(range(2090, 2090 + len(values)))
    return AnnualSeries(
        series_key=f"{platform}:{metric}",
        metric_name=metric,
        platform=platform,
        platform_name="Example",
        years=tuple(years),
        values=tuple(float(v) for v in values),
        ended=ended,
    )


def test_baselines_are_exact():
    train = np.array([10.0, 20.0, 30.0, 40.0])
    assert baselines.naive_last(train, 2).tolist() == [40.0, 40.0]
    assert baselines.historical_mean(train, 1).tolist() == [25.0]
    assert baselines.moving_average(train, 1).tolist() == [30.0]
    # Drift: average change is +10 per step from the last value.
    assert baselines.drift(train, 2).tolist() == [50.0, 60.0]
    trend = baselines.linear_trend(train, 1)
    assert trend[0] == pytest.approx(50.0)


def test_metrics_guard_zero_and_negative_actuals():
    actual = np.array([0.0, 10.0])
    predicted = np.array([5.0, 12.0])
    assert evaluation.mae(actual, predicted) == pytest.approx(3.5)
    assert evaluation.bias(actual, predicted) == pytest.approx(3.5)
    # Sum of |actual| is positive, so WAPE is defined here.
    assert evaluation.wape(actual, predicted) is not None
    negative = np.array([-4.0, 10.0])
    assert evaluation.wape(negative, predicted) is None
    assert evaluation.smape(negative, predicted) is None
    assert evaluation.wape(np.array([0.0, 0.0]), predicted) is None


def test_backtest_never_trains_on_the_target_or_future_years():
    series = _series([10, 12, 14, 16, 18, 20, 22, 24])
    seen_lengths = []

    def spy(train, horizon):
        seen_lengths.append(len(train))
        return baselines.naive_last(train, horizon)

    result = backtest_model(series, "spy", spy, min_train=4)
    assert [fold.target_year for fold in result.folds] == [2094, 2095, 2096, 2097]
    # Each fold's training window ends the year before its target.
    assert seen_lengths == [4, 5, 6, 7]
    assert all(
        fold.train_observations == fold.target_year - series.years[0]
        for fold in result.folds
    )


def test_gap_year_is_never_scored_and_missing_is_not_zero():
    years = (2090, 2091, 2092, 2094, 2095, 2096, 2097)
    series = _series([10, 11, 12, 13, 14, 15, 16], years=years)
    result = backtest_model(series, "naive_last", baselines.naive_last, min_train=3)
    targets = [fold.target_year for fold in result.folds]
    assert 2094 not in targets  # Its predecessor year is missing.
    from forecasting.datasets import _missing_years

    assert _missing_years(years) == (2093,)


def test_short_launch_and_retired_series_are_ineligible():
    launch = evaluate_series(_series([100.0], platform="SYN_NEW"))
    assert launch.status == "ineligible"
    assert "at least 4" in launch.reason
    retired = evaluate_series(_series([10, 9, 8, 7, 6, 5], ended=True))
    assert retired.status == "ineligible"
    assert "retired" in retired.reason


def test_negative_values_are_preserved_and_points_floored_only_for_units():
    series = _series([100, 90, 80, 70, 60, 50, 40, -5])
    outcome = evaluate_series(series, horizon=2)
    assert outcome.status in ("selected", "limited")
    for forecast in outcome.forecasts:
        if forecast["point_clipped"]:
            assert forecast["point_forecast"] == 0.0
    margin = _series([0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.4, -0.5], metric="operating_margin_calculated", platform="CONSOLIDATED")
    margin_outcome = evaluate_series(margin, horizon=1)
    # Margin is an unbounded ratio: no zero floor is applied.
    assert all(not f["point_clipped"] for f in margin_outcome.forecasts)


def test_intervals_use_residual_sigma_and_documented_floor():
    sigma = residual_sigma(np.array([3.0, 4.0]), np.array([1.0, 2.0, 3.0]))
    assert sigma == pytest.approx(np.sqrt(12.5))
    lower, upper, clipped = interval(100.0, 10.0, step=1, metric_name="hw_units_sell_in")
    assert lower == pytest.approx(100 - 1.2816 * 10)
    assert not clipped
    lower, upper, clipped = interval(5.0, 10.0, step=1, metric_name="net_sales_yen")
    assert lower == 0.0 and clipped


def test_build_series_excludes_lifetime_components_and_synthetic():
    annual = pd.DataFrame([
        {"platform_code": "SYN_A", "platform_name": "A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2098, "value_units": 10.0, "period_span": "fiscal_year", "observation_type": "annual_flow", "region_code": "GLOBAL", "include_in_cross_platform_total": True, "source_class": "official_ir"},
        {"platform_code": "SYN_A", "platform_name": "A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": 12.0, "period_span": "fiscal_year", "observation_type": "annual_flow", "region_code": "GLOBAL", "include_in_cross_platform_total": True, "source_class": "official_ir"},
        {"platform_code": "SYN_A", "platform_name": "A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": 999.0, "period_span": "life_to_date", "observation_type": "point_in_time_cumulative", "region_code": "GLOBAL", "include_in_cross_platform_total": True, "source_class": "official_ir"},
        {"platform_code": "SYN_MODEL", "platform_name": "M", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": 5.0, "period_span": "fiscal_year", "observation_type": "annual_flow", "region_code": "GLOBAL", "include_in_cross_platform_total": False, "source_class": "official_ir"},
    ])
    series = build_series(annual, pd.DataFrame())
    assert [item.series_key for item in series] == ["SYN_A:hw_units_sell_in"]
    assert series[0].values == (10.0, 12.0)
    assert series[0].missing_years == ()
    annual.loc[0, "source_class"] = "simulated_operational"
    with pytest.raises(ValueError):
        build_series(annual, pd.DataFrame())


@pytest.mark.integration
def test_forecast_run_persists_in_isolated_schema_only():
    if not database_reachable():
        pytest.skip("PostgreSQL is not running")
    from forecasting.pipeline import run_forecast
    from nih.db import connect

    series = [_series([10, 12, 11, 13, 15, 14, 16, 18, 17, 19], platform="SYN_PERSIST")]
    result = run_forecast(series_list=series, horizon=2)
    assert result.ok, result.error_message
    try:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from forecast.forecasts where run_id = %s", (result.run_id,)
            )
            assert cursor.fetchone()[0] == 2
            cursor.execute(
                """
                select count(*) from mart_reported.mart_annual_platform_performance
                where platform_code = 'SYN_PERSIST'
                """
            )
            assert cursor.fetchone()[0] == 0
    finally:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("delete from forecast.forecast_runs where run_id = %s", (result.run_id,))
            connection.commit()
