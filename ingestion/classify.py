"""Map a printed period label onto the warehouse span.

A cumulative header and a single-quarter header are different spans.
`Q1-Q3` is April 1 through December 31. `Q3` is October 1 through December 31.
An open-ended header such as `FY3/2015~` is rejected rather than stored as a
full fiscal year.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

from nih.periods import PeriodSpan

_LIFE = re.compile(r"^life\s*to\s*date$")
_FY3 = re.compile(r"^fy3/(\d{4})$")
_FY3_OPEN = re.compile(r"^fy3/\d{4}\s*~")
_FY8 = re.compile(r"^fy8/\d{4}$")
_Q_RANGE = re.compile(r"^q([1-4])\s*-\s*q([1-4])$")
_Q_SINGLE = re.compile(r"^q([1-4])$")


@dataclass(frozen=True)
class PrintedPeriod:
    verbatim: str
    accepted: bool
    reason: str | None = None
    period_span: PeriodSpan | None = None
    fiscal_year_ending: int | None = None
    fiscal_quarter: int | None = None


def normalize_label(value: str) -> str:
    text = value.replace("\n", " ").replace("\r", " ")
    for dash in ("–", "—", "−", "‑"):
        text = text.replace(dash, "-")
    text = text.replace("（", "(").replace("）", ")")
    return " ".join(text.split()).strip().casefold()


def classify_period_header(label: str) -> PrintedPeriod | None:
    """Classify a header cell. Return None when the cell is not a period."""

    verbatim = " ".join(label.replace("\n", " ").split()).strip()
    folded = normalize_label(label)
    if not folded:
        return None
    if _LIFE.match(folded):
        return PrintedPeriod(verbatim, True, period_span=PeriodSpan.LIFE_TO_DATE)
    if _FY8.match(folded):
        return PrintedPeriod(
            verbatim,
            False,
            reason="august_fiscal_year",
        )
    if "~" in folded and folded.startswith("fy3/"):
        return PrintedPeriod(verbatim, False, reason="open_ended_column")
    if _FY3_OPEN.match(folded):
        return PrintedPeriod(verbatim, False, reason="open_ended_column")
    year_match = _FY3.match(folded)
    if year_match:
        return PrintedPeriod(
            verbatim,
            True,
            period_span=PeriodSpan.FISCAL_YEAR,
            fiscal_year_ending=int(year_match.group(1)),
        )
    range_match = _Q_RANGE.match(folded)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        span = _cumulative_span(start, end)
        if span is None:
            return PrintedPeriod(verbatim, False, reason="unsupported_quarter_range")
        return PrintedPeriod(verbatim, True, period_span=span)
    single = _Q_SINGLE.match(folded)
    if single:
        quarter = int(single.group(1))
        if quarter == 1:
            return PrintedPeriod(verbatim, True, period_span=PeriodSpan.Q1, fiscal_quarter=None)
        return PrintedPeriod(
            verbatim,
            True,
            period_span=PeriodSpan.QUARTER,
            fiscal_quarter=quarter,
        )
    return None


def _cumulative_span(start: int, end: int) -> PeriodSpan | None:
    if start != 1:
        return None
    if end == 2:
        return PeriodSpan.Q1_Q2
    if end == 3:
        return PeriodSpan.Q1_Q3
    if end == 4:
        return PeriodSpan.FISCAL_YEAR
    return None


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])
