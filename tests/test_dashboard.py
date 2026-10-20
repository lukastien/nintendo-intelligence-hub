from datetime import date

import plotly.graph_objects as go

from dashboards.spans import build_span_figure, span_frame


def test_nine_month_window_starts_in_april_and_q3_starts_in_october():
    frame = span_frame(2026)
    nine_month = frame.loc[frame["label"] == "Nine-month year-to-date"].iloc[0]
    third_quarter = frame.loc[frame["label"] == "Q3 single quarter"].iloc[0]
    assert nine_month["inclusive_start"] == date(2025, 4, 1)
    assert nine_month["inclusive_end"] == date(2025, 12, 31)
    assert third_quarter["inclusive_start"] == date(2025, 10, 1)
    assert third_quarter["inclusive_end"] == date(2025, 12, 31)
    assert set(frame["kind"]) == {"Year-to-date disclosure", "Single-quarter disclosure"}


def test_span_figure_is_a_calendar_chart():
    figure = build_span_figure(2026)
    assert isinstance(figure, go.Figure)
    assert figure.data
    assert figure.layout.yaxis.title.text == "Disclosure span"
