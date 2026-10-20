"""Convert a printed cell to Decimal without replacing a blank with zero."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation


def parse_number(value: object) -> Decimal | None:
    """Return a decimal, or None when the cell is blank or not a number."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace(" ", "")
        if text in {"", "-", "—", "–", "n/a", "na"}:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None
