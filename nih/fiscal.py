"""Nintendo fiscal calendar.

Nintendo's fiscal year ends on March 31. FY3/2026 is April 1, 2025 through
March 31, 2026. Fiscal quarters are April-June, July-September,
October-December, and January-March.
"""

from __future__ import annotations

from datetime import date, timedelta

from nih.errors import GrainError


def fiscal_year_ending(day: date) -> int:
    """Return the calendar year in which this date's fiscal year ends."""

    return day.year + 1 if day.month >= 4 else day.year


def fiscal_quarter(day: date) -> int:
    """Return 1 through 4 for Nintendo's fiscal quarter."""

    if day.month >= 4:
        return ((day.month - 4) // 3) + 1
    return 4


def fiscal_year_bounds(fiscal_year_ending_year: int) -> tuple[date, date]:
    return date(fiscal_year_ending_year - 1, 4, 1), date(fiscal_year_ending_year, 3, 31)


def quarter_bounds(fiscal_year_ending_year: int, quarter: int) -> tuple[date, date]:
    """Inclusive start and end of one fiscal quarter."""

    start_year = fiscal_year_ending_year - 1
    if quarter == 1:
        return date(start_year, 4, 1), date(start_year, 6, 30)
    if quarter == 2:
        return date(start_year, 7, 1), date(start_year, 9, 30)
    if quarter == 3:
        return date(start_year, 10, 1), date(start_year, 12, 31)
    if quarter == 4:
        return date(fiscal_year_ending_year, 1, 1), date(fiscal_year_ending_year, 3, 31)
    raise GrainError("fiscal_quarter must be 1, 2, 3, or 4")


def iter_dates(start: date, end: date):
    if end < start:
        raise GrainError("date range end is on or after the start")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def date_dimension_row(day: date) -> dict:
    """Return one reference-calendar row. This row has no measures."""

    year_ending = fiscal_year_ending(day)
    quarter = fiscal_quarter(day)
    quarter_start, quarter_end = quarter_bounds(year_ending, quarter)
    year_start, year_end = fiscal_year_bounds(year_ending)
    iso = day.isocalendar()
    return {
        "date_key": int(day.strftime("%Y%m%d")),
        "calendar_date": day,
        "calendar_year": day.year,
        "calendar_month": day.month,
        "calendar_quarter": ((day.month - 1) // 3) + 1,
        "iso_year": iso.year,
        "iso_week": iso.week,
        "nintendo_fiscal_year_ending": year_ending,
        "fiscal_label": f"FY3/{year_ending}",
        "fiscal_quarter": quarter,
        "fiscal_quarter_start": quarter_start,
        "fiscal_quarter_end": quarter_end,
        "is_fiscal_quarter_end": day == quarter_end,
        "fiscal_year_start": year_start,
        "fiscal_year_end": year_end,
    }


def build_date_dimension(start: date, end: date) -> list[dict]:
    return [date_dimension_row(day) for day in iter_dates(start, end)]
