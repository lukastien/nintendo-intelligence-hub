"""Shared disclosure fixtures. Values are synthetic and use fiscal year 2099."""

from datetime import date
from decimal import Decimal

from nih.periods import (
    DisclosureMeasure,
    PeriodSpan,
    ProductGrain,
    expected_period_bounds,
)
from nih.provenance import SourceClass


def measure(**overrides) -> DisclosureMeasure:
    payload = {
        "source_document_id": "synthetic_doc",
        "source_class": SourceClass.OFFICIAL_IR,
        "metric_code": "hw_units_sell_in",
        "product_grain": ProductGrain.HARDWARE,
        "platform_code": "SYN_PLATFORM",
        "region_code": "SYN_REGION",
        "game_code": None,
        "fiscal_year_ending": 2099,
        "period_span": PeriodSpan.Q1,
        "fiscal_quarter": None,
        "period_start": date(2098, 4, 1),
        "period_end": date(2098, 6, 30),
        "as_of_date": date(2098, 6, 30),
        "value": Decimal("1000"),
        "is_forecast": False,
        "is_additive_flow": True,
        "is_platform_aggregate": False,
        "is_platform_component": False,
        "parent_platform_code": None,
        "is_region_aggregate": False,
        "sales_basis": "sell_in",
    }
    payload.update(overrides)
    return DisclosureMeasure(**payload)


def ytd(span: PeriodSpan, value: str, document_id: str, as_of: date | None = None) -> DisclosureMeasure:
    start, end = expected_period_bounds(2099, span)
    return measure(
        source_document_id=document_id,
        period_span=span,
        fiscal_quarter=None,
        period_start=start,
        period_end=end,
        as_of_date=as_of or end,
        value=Decimal(value),
    )
