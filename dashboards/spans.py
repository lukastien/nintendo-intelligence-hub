"""Fiscal-span chart. The bars are calendar windows, not sales."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from nih.fiscal import quarter_bounds


def span_frame(fiscal_year_ending: int) -> pd.DataFrame:
    """Return the disclosure windows inside one Nintendo fiscal year.

    The nine-month window starts on April 1. The third fiscal quarter starts
    on October 1. Those two rows are different spans.
    """

    q1_start, q1_end = quarter_bounds(fiscal_year_ending, 1)
    q2_start, q2_end = quarter_bounds(fiscal_year_ending, 2)
    q3_start, q3_end = quarter_bounds(fiscal_year_ending, 3)
    q4_start, q4_end = quarter_bounds(fiscal_year_ending, 4)
    rows = [
        ("Q1 year-to-date (also the first quarter)", "Year-to-date disclosure", q1_start, q1_end),
        ("Q2 single quarter", "Single-quarter disclosure", q2_start, q2_end),
        ("First-half year-to-date", "Year-to-date disclosure", q1_start, q2_end),
        ("Q3 single quarter", "Single-quarter disclosure", q3_start, q3_end),
        ("Nine-month year-to-date", "Year-to-date disclosure", q1_start, q3_end),
        ("Q4 single quarter", "Single-quarter disclosure", q4_start, q4_end),
        ("Fiscal-year total", "Year-to-date disclosure", q1_start, q4_end),
    ]
    frame = pd.DataFrame(rows, columns=["label", "kind", "inclusive_start", "inclusive_end"])
    frame["display_end"] = frame["inclusive_end"].map(lambda day: day + timedelta(days=1))
    frame["fiscal_label"] = f"FY3/{fiscal_year_ending}"
    return frame


def build_span_figure(fiscal_year_ending: int) -> go.Figure:
    frame = span_frame(fiscal_year_ending)
    timeline = frame.assign(
        start=frame["inclusive_start"].map(lambda day: datetime(day.year, day.month, day.day)),
        end=frame["display_end"].map(lambda day: datetime(day.year, day.month, day.day)),
    )
    figure = px.timeline(
        timeline,
        x_start="start",
        x_end="end",
        y="label",
        color="kind",
        hover_data={"inclusive_start": True, "inclusive_end": True, "start": False, "end": False},
        color_discrete_map={
            "Year-to-date disclosure": "#1F4E79",
            "Single-quarter disclosure": "#C47B4A",
        },
    )
    figure.update_yaxes(
        autorange="reversed",
        title="Disclosure span",
        categoryorder="array",
        categoryarray=list(frame["label"]),
    )
    figure.update_xaxes(title="Calendar date")
    figure.update_layout(
        title=f"FY3/{fiscal_year_ending} period spans",
        legend_title="How to read the column",
        height=520,
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
    )
    return figure
