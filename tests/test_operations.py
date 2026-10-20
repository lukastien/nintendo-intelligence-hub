from datetime import date

import pandas as pd
import pytest

from forecasting.baseline import fit_weekly_baseline
from ingestion.simulate import DISCLAIMER, synthetic_weekly_sell_through
from monitoring.checks import (
    aggregate_component_collisions,
    region_aggregate_collisions,
    simulated_zscore_alerts,
)
from nih.errors import ProvenanceError


def test_generator_is_labeled_and_deterministic():
    frame = synthetic_weekly_sell_through()
    assert len(frame) == 48
    assert set(frame["source_class"]) == {"simulated_operational"}
    assert set(frame["disclaimer"]) == {DISCLAIMER}
    assert set(frame["sku_code"]) == {"SYN_SKU_A", "SYN_SKU_B"}
    assert set(frame["region_code"]) == {"SIM_NORTH", "SIM_SOUTH"}
    again = synthetic_weekly_sell_through()
    pd.testing.assert_frame_equal(frame, again)


def test_family_and_component_rows_are_flagged():
    frame = pd.DataFrame(
        [
            _point("NSW_FAMILY", None, True),
            _point("NSW", "NSW_FAMILY", False),
        ]
    )
    collisions = aggregate_component_collisions(frame)
    assert len(collisions) == 1
    assert collisions.iloc[0]["platform_code_aggregate"] == "NSW_FAMILY"
    assert collisions.iloc[0]["platform_code_component"] == "NSW"


def test_global_and_region_rows_are_flagged():
    frame = pd.DataFrame(
        [
            _point("SYN_PLATFORM", None, False, region_code="GLOBAL"),
            _point("SYN_PLATFORM", None, False, region_code="SYN_REGION"),
        ]
    )
    collisions = region_aggregate_collisions(frame)
    assert len(collisions) == 1


def test_zscore_flags_a_synthetic_spike_and_rejects_official_rows():
    rows = []
    for week in range(1, 16):
        rows.append(_week(week, 10))
    rows.append(_week(16, 500))
    alerts = simulated_zscore_alerts(pd.DataFrame(rows))
    assert list(alerts["units"]) == [500]

    official = pd.DataFrame(rows).assign(source_class="official_ir")
    with pytest.raises(ProvenanceError):
        simulated_zscore_alerts(official)


def test_forecast_baseline_accepts_only_the_synthetic_series():
    forecast = fit_weekly_baseline(synthetic_weekly_sell_through(), horizon=4)
    assert len(forecast) == 16
    assert set(forecast["model_name"]) == {"sklearn.linear_regression.week_index"}
    assert forecast["disclaimer"].str.contains("synthetic").all()
    assert forecast["step"].max() == 4

    official = synthetic_weekly_sell_through().assign(source_class="official_ir")
    with pytest.raises(ProvenanceError):
        fit_weekly_baseline(official)


def _point(platform_code, parent, is_aggregate, region_code="SYN_REGION"):
    return {
        "platform_code": platform_code,
        "parent_platform_code": parent,
        "is_platform_aggregate": is_aggregate,
        "region_code": region_code,
        "period_span": "q1",
        "fiscal_year_ending": 2099,
        "metric_code": "hw_units_sell_in",
    }


def _week(week: int, units: int) -> dict:
    return {
        "source_class": "simulated_operational",
        "series_name": "synthetic_spike",
        "sku_code": "SYN_SKU_A",
        "region_code": "SIM_NORTH",
        "iso_year": 2099,
        "iso_week": week,
        "week_start": date(2099, 1, week),
        "units": units,
    }
