"""Display formatting. No figures live here; values arrive from SQL."""

from __future__ import annotations

import math


def fiscal_label(fiscal_year_ending: int | float | None) -> str:
    if fiscal_year_ending is None:
        return "No fiscal year"
    try:
        if math.isnan(float(fiscal_year_ending)):
            return "No fiscal year"
    except (TypeError, ValueError):
        return "No fiscal year"
    return f"FY3/{int(fiscal_year_ending)}"


def format_units(value: float | int | None) -> str:
    if value is None:
        return "Not reported"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not reported"
    if math.isnan(number):
        return "Not reported"
    magnitude = abs(number)
    if magnitude >= 1_000_000_000:
        return f"{number / 1_000_000_000:,.2f}B units"
    if magnitude >= 1_000_000:
        return f"{number / 1_000_000:,.2f}M units"
    if magnitude >= 1_000:
        return f"{number / 1_000:,.1f}K units"
    return f"{number:,.0f} units"


def format_yen(value: float | int | None) -> str:
    if value is None:
        return "Not reported"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not reported"
    if math.isnan(number):
        return "Not reported"
    magnitude = abs(number)
    if magnitude >= 1_000_000_000_000:
        return f"¥{number / 1_000_000_000_000:,.2f}T"
    if magnitude >= 1_000_000_000:
        return f"¥{number / 1_000_000_000:,.1f}B"
    if magnitude >= 1_000_000:
        return f"¥{number / 1_000_000:,.1f}M"
    return f"¥{number:,.0f}"


def format_percent(value: float | None, digits: int = 1) -> str:
    """Format a ratio such as 0.123 as a percentage. None stays unavailable."""
    if value is None:
        return "Not available"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not available"
    if math.isnan(number) or math.isinf(number):
        return "Not available"
    return f"{number * 100:+.{digits}f}%" if digits >= 0 else f"{number * 100}%"


def format_ratio(value: float | None) -> str:
    if value is None:
        return "Not available"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not available"
    if math.isnan(number) or math.isinf(number):
        return "Not available"
    return f"{number:,.2f}×"


def format_count(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def format_timestamp(value) -> str:
    """Short human-readable timestamp, e.g. '20 Oct 2026 · 18:40 UTC'.

    Accepts datetimes, pandas timestamps, and ISO strings. Naive values
    are shown as-is without inventing a timezone; unparseable or missing
    values render as an em dash rather than a raw repr.
    """
    if value is None:
        return "—"
    try:
        import pandas as pd

        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return "—"
    except Exception:
        return str(value)
    suffix = " UTC" if stamp.tzinfo is not None else ""
    return stamp.strftime("%d %b %Y · %H:%M") + suffix
