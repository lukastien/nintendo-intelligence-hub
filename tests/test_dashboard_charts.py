"""Regression tests for the shared Plotly layout.

The frames use invented values. They test layout only: no figure carries
a Plotly title (Streamlit renders the heading), legends sit below the
plot with enough bottom margin, and single-series charts hide legends.
"""

import pandas as pd
import pytest

from dashboards import charts


def _title_text(figure) -> str:
    title = figure.layout.title
    return title.text if title is not None else ""


@pytest.mark.parametrize(
    "figure",
    [
        charts.annual_metric_chart(
            pd.DataFrame(
                [
                    {"fiscal_year_ending": 2098, "metric_code": "hw_units_sell_in", "value_units": 10.0},
                    {"fiscal_year_ending": 2098, "metric_code": "sw_units_sell_in", "value_units": 40.0},
                    {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "value_units": 20.0},
                    {"fiscal_year_ending": 2099, "metric_code": "sw_units_sell_in", "value_units": 50.0},
                ]
            ),
            title="A deliberately long descriptive title that must not be drawn by Plotly",
        ),
        charts.hardware_software_chart(
            pd.DataFrame(
                [{"fiscal_year_ending": 2099, "hardware_units": 10.0, "software_units": 40.0}]
            ),
            platform_name="Example Platform With A Long Name",
        ),
        charts.ratio_chart(
            pd.DataFrame(
                [{"fiscal_year_ending": 2099, "software_units_per_hardware_unit": 4.0}]
            ),
            platform_name="Example",
        ),
        charts.lifetime_chart(
            pd.DataFrame(
                [
                    {"as_of_date": "2099-06-30", "metric_code": "hw_units_sell_in", "value_units": 10.0},
                    {"as_of_date": "2099-06-30", "metric_code": "sw_units_sell_in", "value_units": 40.0},
                ]
            ),
            platform_name="Example",
        ),
        charts.regional_chart(
            pd.DataFrame(
                [
                    {"fiscal_year_ending": 2099, "region_code": "JPN", "value_units": 1.0, "region_layout": "europe_split", "reconciliation_status": "exact"},
                    {"fiscal_year_ending": 2099, "region_code": "EUR", "value_units": 2.0, "region_layout": "europe_split", "reconciliation_status": "exact"},
                    {"fiscal_year_ending": 2099, "region_code": "AMR", "value_units": 3.0, "region_layout": "europe_split", "reconciliation_status": "exact"},
                    {"fiscal_year_ending": 2099, "region_code": "OTH", "value_units": 4.0, "region_layout": "europe_split", "reconciliation_status": "exact"},
                ]
            ),
            title="Regional",
        ),
        charts.financial_chart(
            pd.DataFrame(
                [
                    {
                        "fiscal_year_ending": 2099,
                        "net_sales_yen": 100.0,
                        "operating_profit_yen": 10.0,
                        "ordinary_profit_yen": 11.0,
                        "profit_attributable_to_owners_yen": 8.0,
                    }
                ]
            )
        ),
        charts.margin_chart(
            pd.DataFrame(
                [
                    {
                        "fiscal_year_ending": 2099,
                        "operating_margin_calculated": 0.1,
                        "profit_margin_calculated": 0.08,
                    }
                ]
            )
        ),
        charts.platform_comparison_chart(
            pd.DataFrame(
                [{"platform_name": "Example", "value_units": 10.0}]
            ),
            2099,
            title="Comparison",
        ),
        charts.annual_metric_chart(pd.DataFrame(), title="Empty"),
    ],
)
def test_every_chart_has_no_plotly_title_and_room_below_the_plot(figure):
    assert not _title_text(figure)
    assert figure.layout.height == charts.CHART_HEIGHT
    # No top margin is reserved for a title/legend band any more.
    assert figure.layout.margin.t <= 30
    # There is always room under the axes for tick labels and, when shown,
    # a horizontal legend below the plotting area.
    assert figure.layout.margin.b >= 60
    if figure.layout.showlegend:
        legend = figure.layout.legend
        assert legend.orientation == "h"
        assert legend.y is not None and legend.y < 0
        assert legend.font.size == 11
        # Wrapped entries get a taller bottom margin than one short row.
        assert figure.layout.margin.b >= 80


def test_single_series_charts_hide_the_legend():
    comparison = charts.platform_comparison_chart(
        pd.DataFrame([{"platform_name": "Example", "value_units": 10.0}]),
        2099,
        title="Comparison",
    )
    assert not comparison.layout.showlegend
    ratio = charts.ratio_chart(
        pd.DataFrame([{"fiscal_year_ending": 2099, "software_units_per_hardware_unit": 4.0}]),
        platform_name="Example",
    )
    assert not ratio.layout.showlegend


def test_legend_labels_are_short_and_defined_elsewhere():
    figure = charts.financial_chart(
        pd.DataFrame(
            [
                {
                    "fiscal_year_ending": 2099,
                    "net_sales_yen": 100.0,
                    "operating_profit_yen": 10.0,
                    "ordinary_profit_yen": 11.0,
                    "profit_attributable_to_owners_yen": 8.0,
                }
            ]
        )
    )
    names = {trace.name for trace in figure.data}
    assert names == {"Net sales", "Operating profit", "Ordinary profit", "Owners' profit"}
    assert all(len(name) <= 20 for name in names)

    annual = charts.annual_metric_chart(
        pd.DataFrame(
            [
                {"fiscal_year_ending": 2099, "metric_code": "hw_units_sell_in", "value_units": 10.0},
                {"fiscal_year_ending": 2099, "metric_code": "sw_units_sell_in", "value_units": 40.0},
            ]
        ),
        title="Annual",
    )
    assert {trace.name for trace in annual.data} == {"Hardware", "Software"}
