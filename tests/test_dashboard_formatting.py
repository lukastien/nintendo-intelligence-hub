"""Dashboard formatting and stale-module regression tests."""

import dashboards.queries as queries
from dashboards.app import _query_attr
from dashboards.formatting import format_timestamp


def test_format_timestamp_is_short_and_human_readable():
    assert format_timestamp("2026-10-20 18:40:15.123456+00:00") == "20 Oct 2026 · 18:40 UTC"
    assert format_timestamp(None) == "—"
    assert format_timestamp("not a date") == "not a date"


def test_forecast_query_functions_exist_and_reload_heals_stale_module():
    for name in ("forecast_runs", "forecasts_for_run", "series_evaluations_for_run", "backtest_folds_for_run"):
        assert callable(_query_attr(name))
    # Simulate a long-running server holding a pre-Phase-7 queries module:
    # deleting the attribute must be healed by the reload in _query_attr.
    original = queries.forecast_runs
    del queries.forecast_runs
    try:
        healed = _query_attr("forecast_runs")
        assert callable(healed)
    finally:
        queries.forecast_runs = original
