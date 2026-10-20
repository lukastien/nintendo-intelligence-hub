"""Tableau-ready exports from the official marts.

The export reads PostgreSQL at run time. It does not embed figures in
source code and it does not export the synthetic weekly series into an
official file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dashboards import queries
from dashboards.definitions import METRIC_DEFINITIONS


def export_frames() -> dict[str, pd.DataFrame]:
    return {
        "annual_platform_performance": queries.annual_performance(),
        "hardware_software_trends": queries.hardware_software_trends(),
        "regional_performance": queries.regional_performance(),
        "financial_performance": queries.financial_performance(),
        "lifetime_platform_sales": queries.lifetime_platform_sales(),
        "metric_definitions": pd.DataFrame(
            [
                {"metric_code": code, **values}
                for code, values in METRIC_DEFINITIONS.items()
            ]
        ),
    }


def write_exports(output_dir: Path) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, frame in export_frames().items():
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        counts[name] = len(frame)
    return counts
