from datetime import date

import pytest

from nih.fiscal import (
    build_date_dimension,
    fiscal_quarter,
    fiscal_year_bounds,
    fiscal_year_ending,
    quarter_bounds,
)


def test_fiscal_year_turns_on_april_1():
    assert fiscal_year_ending(date(2026, 3, 31)) == 2026
    assert fiscal_quarter(date(2026, 3, 31)) == 4
    assert fiscal_year_ending(date(2026, 4, 1)) == 2027
    assert fiscal_quarter(date(2026, 4, 1)) == 1
    assert fiscal_year_ending(date(2026, 10, 20)) == 2027
    assert fiscal_quarter(date(2026, 10, 20)) == 3


def test_quarter_bounds_cover_the_fiscal_year_without_overlap():
    bounds = [quarter_bounds(2026, quarter) for quarter in (1, 2, 3, 4)]
    assert bounds[0] == (date(2025, 4, 1), date(2025, 6, 30))
    assert bounds[1] == (date(2025, 7, 1), date(2025, 9, 30))
    assert bounds[2] == (date(2025, 10, 1), date(2025, 12, 31))
    assert bounds[3] == (date(2026, 1, 1), date(2026, 3, 31))
    assert fiscal_year_bounds(2026) == (date(2025, 4, 1), date(2026, 3, 31))


def test_date_dimension_labels_a_non_leap_fiscal_year():
    start, end = fiscal_year_bounds(2026)
    rows = build_date_dimension(start, end)
    assert len(rows) == 365
    assert {row["fiscal_label"] for row in rows} == {"FY3/2026"}
    assert rows[0]["fiscal_quarter"] == 1
    assert rows[-1]["is_fiscal_quarter_end"] is True
    assert rows[-1]["fiscal_quarter"] == 4


def test_invalid_quarter_is_rejected():
    with pytest.raises(ValueError):
        quarter_bounds(2026, 5)
