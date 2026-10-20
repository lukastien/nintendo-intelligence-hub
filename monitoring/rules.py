"""Configurable monitoring thresholds.

The defaults are deliberately conservative. Business movements are
informational signals, not errors, and known Nintendo reporting
differences are excluded before any threshold is applied:

- negative annual units are kept as disclosed returns or revisions;
- a regional breakdown labelled incomplete is a known older-sheet
  condition, not a reconciliation failure;
- regional sums that match within one printed unit (the source scale)
  are reporting precision, not discrepancies;
- family totals and component models are supposed to coexist, so only
  their *summed* use would be wrong, which the marts prevent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    # Business anomalies (severity info).
    yoy_change: float = 0.50
    robust_z: float = 3.5
    robust_min_history: int = 5
    margin_change_points: float = 0.05

    # Data quality (severity warning unless an integrity rule says critical).
    regional_relative_deviation: float = 0.001
    regional_absolute_units: float = 10_000.0
    row_count_relative_change: float = 0.20
    row_count_absolute_change: int = 10

    @classmethod
    def from_env(cls) -> "Thresholds":
        def number(name: str, fallback: float) -> float:
            raw = os.environ.get(name, "").strip()
            if not raw:
                return fallback
            try:
                return float(raw)
            except ValueError:
                return fallback

        defaults = cls()
        return cls(
            yoy_change=number("NIH_MONITOR_YOY_CHANGE", defaults.yoy_change),
            robust_z=number("NIH_MONITOR_ROBUST_Z", defaults.robust_z),
            robust_min_history=int(number("NIH_MONITOR_ROBUST_MIN_HISTORY", defaults.robust_min_history)),
            margin_change_points=number("NIH_MONITOR_MARGIN_CHANGE_POINTS", defaults.margin_change_points),
            regional_relative_deviation=number(
                "NIH_MONITOR_REGIONAL_RELATIVE_DEVIATION", defaults.regional_relative_deviation
            ),
            regional_absolute_units=number(
                "NIH_MONITOR_REGIONAL_ABSOLUTE_UNITS", defaults.regional_absolute_units
            ),
            row_count_relative_change=number(
                "NIH_MONITOR_ROW_COUNT_RELATIVE_CHANGE", defaults.row_count_relative_change
            ),
            row_count_absolute_change=int(
                number("NIH_MONITOR_ROW_COUNT_ABSOLUTE_CHANGE", defaults.row_count_absolute_change)
            ),
        )
