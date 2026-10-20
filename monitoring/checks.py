"""Structural monitors for double-counting and simulated-series spikes."""

from __future__ import annotations

import pandas as pd

from nih.errors import ProvenanceError
from nih.provenance import assert_simulated_frame


def aggregate_component_collisions(frame: pd.DataFrame) -> pd.DataFrame:
    """Return keys where a family total and one of its components share a period.

    The monitor does not change values. A family total already includes the
    component, so those rows stay separate in any later sum.
    """

    required = {
        "platform_code",
        "parent_platform_code",
        "is_platform_aggregate",
        "region_code",
        "period_span",
        "fiscal_year_ending",
        "metric_code",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ProvenanceError(f"collision check is missing {sorted(missing)}")
    if frame.empty:
        return frame.iloc[0:0]
    aggregates = frame.loc[frame["is_platform_aggregate"]].copy()
    components = frame.loc[frame["parent_platform_code"].notna()].copy()
    if aggregates.empty or components.empty:
        return frame.iloc[0:0]
    merged = components.merge(
        aggregates,
        left_on=["parent_platform_code", "region_code", "period_span", "fiscal_year_ending", "metric_code"],
        right_on=["platform_code", "region_code", "period_span", "fiscal_year_ending", "metric_code"],
        suffixes=("_component", "_aggregate"),
    )
    if merged.empty:
        return merged
    return merged[
        [
            "metric_code",
            "fiscal_year_ending",
            "period_span",
            "region_code",
            "platform_code_aggregate",
            "platform_code_component",
        ]
    ].drop_duplicates()


def region_aggregate_collisions(frame: pd.DataFrame) -> pd.DataFrame:
    """Return keys where GLOBAL and a regional row share a platform and period."""

    required = {"region_code", "platform_code", "period_span", "fiscal_year_ending", "metric_code"}
    missing = required.difference(frame.columns)
    if missing:
        raise ProvenanceError(f"region check is missing {sorted(missing)}")
    totals = frame.loc[frame["region_code"] == "GLOBAL"]
    parts = frame.loc[frame["region_code"] != "GLOBAL"]
    if totals.empty or parts.empty:
        return frame.iloc[0:0]
    merged = parts.merge(
        totals,
        on=["platform_code", "period_span", "fiscal_year_ending", "metric_code"],
        suffixes=("_region", "_global"),
    )
    if merged.empty:
        return merged
    return merged[
        [
            "metric_code",
            "fiscal_year_ending",
            "period_span",
            "platform_code",
            "region_code_region",
        ]
    ].drop_duplicates()


def simulated_zscore_alerts(frame: pd.DataFrame, threshold: float = 3.0) -> pd.DataFrame:
    """Flag weekly synthetic points whose z-score reaches the threshold."""

    required = {"source_class", "series_name", "sku_code", "region_code", "iso_year", "iso_week", "units"}
    missing = required.difference(frame.columns)
    if missing:
        raise ProvenanceError(f"anomaly check is missing {sorted(missing)}")
    assert_simulated_frame(set(frame["source_class"]), set(frame["series_name"]))
    alerts: list[pd.DataFrame] = []
    grouped = frame.groupby(["series_name", "sku_code", "region_code"], dropna=False)
    for _, group in grouped:
        deviation = group["units"].std(ddof=1)
        if pd.isna(deviation) or deviation == 0:
            continue
        scored = group.copy()
        scored["z_score"] = (scored["units"] - scored["units"].mean()) / deviation
        flagged = scored.loc[scored["z_score"].abs() >= threshold]
        if not flagged.empty:
            alerts.append(flagged)
    if not alerts:
        return frame.iloc[0:0]
    return pd.concat(alerts, ignore_index=True)
