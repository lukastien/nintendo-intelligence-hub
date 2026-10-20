"""Pandas wrapper around the tested year-to-date derivation."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from nih.periods import DisclosureMeasure, derive_reported_incremental


def disclosures_to_incremental(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate official disclosure rows and return derived quarters.

    The input values are already normalized. An empty frame returns an empty
    frame. Gaps are omitted here; callers that need them use
    `derive_reported_incremental` directly.
    """

    if frame.empty:
        return pd.DataFrame()
    rows: list[DisclosureMeasure] = []
    for record in frame.to_dict(orient="records"):
        cleaned = {}
        for key, value in record.items():
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cleaned[key] = None
                continue
            if hasattr(value, "to_pydatetime"):
                value = value.to_pydatetime()
            if isinstance(value, datetime):
                value = value.date()
            cleaned[key] = value
        if cleaned.get("game_code") == "":
            cleaned["game_code"] = None
        rows.append(DisclosureMeasure.model_validate(cleaned))
    result = derive_reported_incremental(rows)
    return pd.DataFrame([quarter.model_dump() for quarter in result.quarters])
