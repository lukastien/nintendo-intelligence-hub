"""Deterministic synthetic weekly sell-through.

The series is a small arithmetic pattern used to exercise the simulated
schema, anomaly check, and forecast baseline. The quantities are not an
estimate of Nintendo sales.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

DISCLAIMER = (
    "Synthetic demonstration series generated for pipeline tests. "
    "It is not a Nintendo result, estimate, or disclosure."
)
SERIES_NAME = "synthetic_demo_weekly"
SKUS = ("SYN_SKU_A", "SYN_SKU_B")
REGIONS = ("SIM_NORTH", "SIM_SOUTH")
CHANNEL = "SIM_RETAIL"


def synthetic_weekly_sell_through(weeks: int = 12) -> pd.DataFrame:
    """Return `weeks` ISO weeks for two SKUs and two simulated regions."""

    if weeks < 2:
        raise ValueError("the synthetic series contains at least two weeks")
    start = date(2024, 1, 1)
    if start.weekday() != 0:
        raise ValueError("the generator starts on a Monday")
    rows = []
    for week_index in range(weeks):
        week_start = start + timedelta(days=7 * week_index)
        iso = week_start.isocalendar()
        for sku_index, sku_code in enumerate(SKUS):
            for region_index, region_code in enumerate(REGIONS):
                units = 20 + week_index + (5 * sku_index) + (3 * region_index)
                rows.append(
                    {
                        "source_class": "simulated_operational",
                        "series_name": SERIES_NAME,
                        "iso_year": iso.year,
                        "iso_week": iso.week,
                        "week_start": week_start,
                        "sku_code": sku_code,
                        "region_code": region_code,
                        "channel_code": CHANNEL,
                        "units": units,
                        "disclaimer": DISCLAIMER,
                    }
                )
    return pd.DataFrame(rows)
