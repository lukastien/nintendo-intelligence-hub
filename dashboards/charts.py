"""Plotly charts with one visual language.

Descriptive titles live in Streamlit, above the chart (see
``dashboards.app._chart_block``). Figures therefore carry no Plotly title:
the legend sits below the plotting area with a bottom margin sized to the
number of legend rows, so a title, a legend, and the axes can never share
the same band. Empty frames produce a labeled figure instead of a
fabricated series. Annual flows and life-to-date snapshots are charted by
separate calls.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

RED = "#E60012"
CHARCOAL = "#232326"
SLATE = "#5B6470"
BLUE = "#2563A8"
TEAL = "#0E7C7B"
LIGHT = "#E8E8E6"

COLOR_SEQUENCE = [RED, BLUE, TEAL, "#7A5C00", "#6D4C9F", SLATE]
CHART_HEIGHT = 380

_METRIC_LABELS = {
    "hw_units_sell_in": "Hardware",
    "sw_units_sell_in": "Software",
}

_FINANCIAL_LABELS = {
    "net_sales_yen": "Net sales",
    "operating_profit_yen": "Operating profit",
    "ordinary_profit_yen": "Ordinary profit",
    "profit_attributable_to_owners_yen": "Owners' profit",
}

_MARGIN_LABELS = {
    "operating_margin_calculated": "Operating margin",
    "profit_margin_calculated": "Net profit margin",
}

_REGION_LABELS = {
    "JPN": "Japan",
    "AMR": "Americas",
    "EUR": "Europe",
    "OTH": "Other",
    "OTH_INCL_EUROPE": "Other incl. Europe",
    "GLOBAL": "Worldwide",
}


def _legend_rows(entry_count: int) -> int:
    """Legend rows when entries are laid out at most two per row."""
    if entry_count <= 2:
        return entry_count
    return math.ceil(entry_count / 2)


def _layout(
    figure: go.Figure,
    y_title: str = "",
    x_title: str = "",
    *,
    legend_entries: int = 0,
) -> go.Figure:
    """Shared layout. No figure title; legend below the plot.

    ``legend_entries`` is the number of legend items. The bottom margin
    grows with the number of wrapped legend rows so nothing is clipped.
    """
    show_legend = legend_entries > 1
    bottom = 60
    legend = {"visible": False}
    if show_legend:
        rows = _legend_rows(legend_entries)
        bottom = 64 + rows * 26
        legend = {
            "orientation": "h",
            "yanchor": "top",
            "y": -0.16,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
            "title": {"text": ""},
            "entrywidthmode": "fraction",
            "entrywidth": 0.48 if legend_entries > 2 else 0.3,
            "tracegroupgap": 4,
        }
    figure.update_layout(
        title=None,
        font={
            "family": "Inter, -apple-system, 'Segoe UI', sans-serif",
            "color": CHARCOAL,
            "size": 12,
        },
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=CHART_HEIGHT,
        autosize=True,
        margin={"l": 48, "r": 24, "t": 28, "b": bottom},
        legend=legend,
        showlegend=show_legend,
        hovermode="x unified",
    )
    figure.update_xaxes(
        title={"text": x_title, "font": {"size": 12}},
        tickfont={"size": 11},
        gridcolor=LIGHT,
        linecolor=LIGHT,
        automargin=True,
    )
    figure.update_yaxes(
        title={"text": y_title, "font": {"size": 12}},
        tickfont={"size": 11},
        gridcolor=LIGHT,
        linecolor=LIGHT,
        zerolinecolor=LIGHT,
        automargin=True,
    )
    return figure


def _empty(title: str, message: str = "Not reported for this selection") -> go.Figure:
    # ``title`` is accepted for call-site readability; the visible heading is
    # rendered by Streamlit, so the figure repeats only the empty message.
    del title
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"color": SLATE, "size": 13},
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return _layout(figure)


def annual_metric_chart(frame: pd.DataFrame, *, title: str, metric_label: str = "Units") -> go.Figure:
    data = frame.dropna(subset=["value_units"]) if not frame.empty and "value_units" in frame else frame
    if data.empty:
        return _empty(title)
    data = data.assign(series=data["metric_code"].map(_METRIC_LABELS).fillna(data["metric_code"]))
    series_count = int(data["series"].nunique())
    figure = px.line(
        data.sort_values("fiscal_year_ending"),
        x="fiscal_year_ending",
        y="value_units",
        color="series" if series_count > 1 else None,
        markers=True,
        color_discrete_sequence=COLOR_SEQUENCE,
        labels={"fiscal_year_ending": "Fiscal year ending", "value_units": metric_label, "series": "Metric"},
    )
    return _layout(figure, metric_label, "Fiscal year ending (March 31)", legend_entries=series_count)


def platform_comparison_chart(frame: pd.DataFrame, fiscal_year: int, *, title: str) -> go.Figure:
    data = frame.dropna(subset=["value_units"]) if not frame.empty else frame
    if data.empty:
        return _empty(title, f"Not reported for FY3/{fiscal_year}")
    data = data.sort_values("value_units", ascending=True)
    figure = px.bar(
        data,
        x="value_units",
        y="platform_name",
        orientation="h",
        color_discrete_sequence=[RED],
        labels={"value_units": "Units", "platform_name": "Platform"},
    )
    # One bar series: no legend competes with the axis labels.
    return _layout(figure, "", "Units")


def hardware_software_chart(frame: pd.DataFrame, *, platform_name: str) -> go.Figure:
    if frame.empty:
        return _empty(f"{platform_name}: hardware and software")
    melted = frame.melt(
        id_vars=["fiscal_year_ending"],
        value_vars=[column for column in ("hardware_units", "software_units") if column in frame.columns],
        var_name="metric",
        value_name="units",
    ).dropna(subset=["units"])
    if melted.empty:
        return _empty(f"{platform_name}: hardware and software")
    melted["metric"] = melted["metric"].map({"hardware_units": "Hardware", "software_units": "Software"})
    figure = px.bar(
        melted.sort_values("fiscal_year_ending"),
        x="fiscal_year_ending",
        y="units",
        color="metric",
        barmode="group",
        color_discrete_sequence=COLOR_SEQUENCE,
        labels={"fiscal_year_ending": "Fiscal year ending", "units": "Units", "metric": "Metric"},
    )
    return _layout(figure, "Units", "Fiscal year ending (March 31)", legend_entries=2)


def ratio_chart(frame: pd.DataFrame, *, platform_name: str) -> go.Figure:
    data = frame.dropna(subset=["software_units_per_hardware_unit"]) if not frame.empty and "software_units_per_hardware_unit" in frame else frame.iloc[0:0]
    if data.empty:
        return _empty(f"{platform_name}: software per hardware unit", "Ratio unavailable where hardware is zero or missing")
    figure = px.line(
        data.sort_values("fiscal_year_ending"),
        x="fiscal_year_ending",
        y="software_units_per_hardware_unit",
        markers=True,
        color_discrete_sequence=[BLUE],
        labels={"fiscal_year_ending": "Fiscal year ending", "software_units_per_hardware_unit": "Software ÷ hardware"},
    )
    return _layout(figure, "Ratio", "Fiscal year ending (March 31)")


def lifetime_chart(frame: pd.DataFrame, *, platform_name: str) -> go.Figure:
    data = frame.dropna(subset=["value_units"]) if not frame.empty else frame
    if data.empty:
        return _empty(f"{platform_name}: life-to-date snapshots")
    data = data.assign(series=data["metric_code"].map(_METRIC_LABELS).fillna(data["metric_code"]))
    figure = px.bar(
        data.sort_values("as_of_date"),
        x="as_of_date",
        y="value_units",
        color="series",
        barmode="group",
        color_discrete_sequence=COLOR_SEQUENCE,
        labels={"as_of_date": "As-of date", "value_units": "Cumulative units", "series": "Metric"},
    )
    return _layout(figure, "Cumulative units", "As-of date", legend_entries=int(data["series"].nunique()))


def regional_chart(frame: pd.DataFrame, *, title: str) -> go.Figure:
    data = frame.dropna(subset=["value_units"]) if not frame.empty else frame
    if data.empty:
        return _empty(title)
    data = data.assign(region_label=data["region_code"].map(_REGION_LABELS).fillna(data["region_code"]))
    figure = px.bar(
        data.sort_values(["fiscal_year_ending", "region_code"]),
        x="fiscal_year_ending",
        y="value_units",
        color="region_label",
        barmode="group",
        color_discrete_sequence=COLOR_SEQUENCE,
        labels={"fiscal_year_ending": "Fiscal year ending", "value_units": "Units", "region_label": "Region"},
        hover_data=["region_layout", "reconciliation_status"] if "region_layout" in data else None,
    )
    return _layout(figure, "Units", "Fiscal year ending (March 31)", legend_entries=int(data["region_label"].nunique()))


def financial_chart(frame: pd.DataFrame, *, title: str = "Consolidated annual financial performance (JPY)") -> go.Figure:
    if frame.empty:
        return _empty(title)
    melted = frame.melt(
        id_vars=["fiscal_year_ending"],
        value_vars=[c for c in ("net_sales_yen", "operating_profit_yen", "ordinary_profit_yen", "profit_attributable_to_owners_yen") if c in frame.columns],
        var_name="metric",
        value_name="yen",
    ).dropna(subset=["yen"])
    if melted.empty:
        return _empty(title)
    melted["metric"] = melted["metric"].map(_FINANCIAL_LABELS)
    figure = px.line(
        melted.sort_values("fiscal_year_ending"),
        x="fiscal_year_ending",
        y="yen",
        color="metric",
        markers=True,
        color_discrete_sequence=COLOR_SEQUENCE,
        labels={"fiscal_year_ending": "Fiscal year ending", "yen": "JPY", "metric": "Metric"},
    )
    return _layout(figure, "JPY", "Fiscal year ending (March 31)", legend_entries=int(melted["metric"].nunique()))


def margin_chart(frame: pd.DataFrame, *, title: str = "Calculated consolidated margins") -> go.Figure:
    if frame.empty:
        return _empty(title)
    melted = frame.melt(
        id_vars=["fiscal_year_ending"],
        value_vars=[c for c in ("operating_margin_calculated", "profit_margin_calculated") if c in frame.columns],
        var_name="margin",
        value_name="ratio",
    ).dropna(subset=["ratio"])
    if melted.empty:
        return _empty(title)
    melted["margin"] = melted["margin"].map(_MARGIN_LABELS)
    figure = px.line(
        melted.sort_values("fiscal_year_ending"),
        x="fiscal_year_ending",
        y="ratio",
        color="margin",
        markers=True,
        color_discrete_sequence=COLOR_SEQUENCE,
        labels={"fiscal_year_ending": "Fiscal year ending", "ratio": "Margin", "margin": "Margin"},
    )
    figure.update_yaxes(tickformat=".0%")
    return _layout(figure, "Margin", "Fiscal year ending (March 31)", legend_entries=int(melted["margin"].nunique()))
