"""Dashboard calculation and query tests.

Frames below use fiscal year 2098/2099 and synthetic platform codes. They
test arithmetic only and are not Nintendo results. Live query tests skip
when PostgreSQL is not running.
"""

import pandas as pd
import pytest

from dashboards import calculations as calc
from dashboards import queries
from dashboards.formatting import format_percent, format_units, format_yen


def _annual(rows):
    return pd.DataFrame(rows)


def test_cross_platform_total_excludes_component_models():
    frame = _annual([
        {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "platform_code": "FAMILY", "region_code": "GLOBAL", "value_units": 100.0, "include_in_cross_platform_total": True, "observation_type": "annual_flow", "period_span": "fiscal_year"},
        {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "platform_code": "MODEL_A", "region_code": "GLOBAL", "value_units": 60.0, "include_in_cross_platform_total": False, "observation_type": "annual_flow", "period_span": "fiscal_year"},
        {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "platform_code": "OTHER", "region_code": "GLOBAL", "value_units": 20.0, "include_in_cross_platform_total": True, "observation_type": "annual_flow", "period_span": "fiscal_year"},
        {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "platform_code": "FAMILY", "region_code": "JPN", "value_units": 999.0, "include_in_cross_platform_total": True, "observation_type": "annual_flow", "period_span": "fiscal_year"},
    ])
    assert calc.cross_platform_total(frame, 2099, "hw_units_sell_in") == 120.0
    assert calc.cross_platform_total(frame, 2098, "hw_units_sell_in") is None


def test_comparable_yoy_requires_the_same_platform_set():
    base = [
        {"fiscal_year_ending": 2098, "metric_code": "hw_units_sell_in", "platform_code": "A", "region_code": "GLOBAL", "value_units": 100.0, "include_in_cross_platform_total": True, "observation_type": "annual_flow", "period_span": "fiscal_year"},
        {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "platform_code": "A", "region_code": "GLOBAL", "value_units": 125.0, "include_in_cross_platform_total": True, "observation_type": "annual_flow", "period_span": "fiscal_year"},
    ]
    result = calc.comparable_yoy(_annual(base), 2099, "hw_units_sell_in")
    assert result is not None and result["growth"] == pytest.approx(0.25)
    launched = base + [
        {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "platform_code": "B", "region_code": "GLOBAL", "value_units": 10.0, "include_in_cross_platform_total": True, "observation_type": "annual_flow", "period_span": "fiscal_year"},
    ]
    assert calc.comparable_yoy(_annual(launched), 2099, "hw_units_sell_in") is None


def test_ratio_and_margin_reject_zero_denominators():
    assert calc.software_hardware_ratio(0, 100) is None
    assert calc.software_hardware_ratio(None, 100) is None
    assert calc.software_hardware_ratio(50, 100) == 2.0
    assert calc.margin(10, 0) is None
    assert calc.margin(10, 40) == 0.25


def test_regional_share_is_unavailable_for_an_incomplete_breakdown():
    assert calc.regional_share(10, 100, "incomplete_breakdown") is None
    assert calc.regional_share(10, 100, "exact") == pytest.approx(0.1)
    assert calc.regional_share(10, 0, "exact") is None


def test_lifetime_filter_never_returns_annual_rows():
    frame = pd.DataFrame([
        {"platform_code": "A", "region_code": "GLOBAL", "metric_code": "hw_units_sell_in", "value_units": 5.0, "observation_type": "annual_flow", "period_span": "fiscal_year", "is_latest_as_of": False},
        {"platform_code": "A", "region_code": "GLOBAL", "metric_code": "hw_units_sell_in", "value_units": 50.0, "observation_type": "point_in_time_cumulative", "period_span": "life_to_date", "is_latest_as_of": True},
        {"platform_code": "A", "region_code": "GLOBAL", "metric_code": "hw_units_sell_in", "value_units": 40.0, "observation_type": "point_in_time_cumulative", "period_span": "life_to_date", "is_latest_as_of": False},
    ])
    life = calc.filter_lifetime(frame, platforms="A")
    assert list(life["value_units"]) == [50.0, 40.0]
    assert list(calc.filter_lifetime(frame, platforms="A", latest_only=True)["value_units"]) == [50.0]
    annual = calc.filter_annual(frame)
    assert list(annual["value_units"]) == [5.0]


def test_financial_lookup_and_yoy_blanks():
    frame = pd.DataFrame([
        {"fiscal_year_ending": 2098, "net_sales_yen": 100.0, "operating_profit_yen": 10.0, "ordinary_profit_yen": 11.0, "profit_attributable_to_owners_yen": 8.0, "operating_margin_calculated": 0.1, "profit_margin_calculated": 0.08},
        {"fiscal_year_ending": 2099, "net_sales_yen": 200.0, "operating_profit_yen": 50.0, "ordinary_profit_yen": 52.0, "profit_attributable_to_owners_yen": 40.0, "operating_margin_calculated": 0.25, "profit_margin_calculated": 0.2},
    ])
    assert calc.financial_for_year(frame, 2099)["operating_margin"] == pytest.approx(0.25)
    assert calc.financial_for_year(frame, 2000) is None
    grown = calc.add_yoy(frame, "net_sales_yen", [])
    assert pd.isna(grown.iloc[0]["net_sales_yen_growth"])
    assert grown.iloc[1]["net_sales_yen_growth"] == pytest.approx(1.0)


def test_formatting_keeps_missing_values_unavailable():
    assert format_units(None) == "Not reported"
    assert format_yen(None) == "Not reported"
    assert format_percent(None) == "Not available"
    assert format_percent(0.125, 1) == "+12.5%"


@pytest.mark.integration
def test_live_queries_read_only_the_official_marts():
    if not queries.database_available():
        pytest.skip("PostgreSQL is not running")
    annual = queries.annual_performance(platforms=["NSW_FAMILY"], regions=["GLOBAL"], metrics=["hw_units_sell_in"])
    assert not annual.empty
    assert set(annual["source_class"]) == {"official_ir"}
    assert set(annual["period_span"]) == {"fiscal_year"}
    assert not annual["platform_code"].str.startswith("SYN").any()

    trends = queries.hardware_software_trends(platforms=["NSW_FAMILY"], regions=["GLOBAL"])
    assert not trends.empty
    assert (trends["fiscal_year_ending"].diff().dropna() >= 0).all()

    regional = queries.regional_performance(platforms=["NSW_FAMILY"], region_layouts=["europe_split"])
    assert not regional.empty
    assert not (regional["region_code"] == "GLOBAL").any()
    assert set(regional["region_layout"]) == {"europe_split"}

    lifetime = queries.lifetime_platform_sales(platforms=["NSW_FAMILY"], regions=["GLOBAL"])
    assert not lifetime.empty
    assert set(lifetime["period_span"]) == {"life_to_date"}
    assert lifetime["fiscal_year_ending"].isna().all()

    financial = queries.financial_performance()
    assert not financial.empty
    assert set(financial["source_class"]) == {"official_ir"}

    counts = queries.warehouse_counts()
    assert counts["official_unit_rows"] > 0
    assert counts["simulated_rows"] == counts["simulated_mart_rows"]

    runs = queries.pipeline_runs(5)
    assert "status" in runs.columns
