"""Period spans and the year-to-date to quarter derivation.

A Nintendo earnings column labeled Q1-Q3 covers April 1 through December 31.
The October-December quarter is a different span. This module keeps those
spans apart and derives a quarter only from adjacent year-to-date totals.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from nih.errors import GrainError, ProvenanceError
from nih.fiscal import fiscal_year_bounds, quarter_bounds
from nih.provenance import SourceClass, assert_reported_mart_source


class PeriodSpan(str, Enum):
    Q1 = "q1"
    Q1_Q2 = "q1_q2"
    Q1_Q3 = "q1_q3"
    FISCAL_YEAR = "fiscal_year"
    QUARTER = "quarter"
    LIFE_TO_DATE = "life_to_date"
    FORECAST_FISCAL_YEAR = "forecast_fiscal_year"


class ProductGrain(str, Enum):
    HARDWARE = "hardware"
    SOFTWARE_TOTAL = "software_total"
    SOFTWARE_TITLE = "software_title"
    FINANCIAL_LINE = "financial_line"


class QualityFlag(str, Enum):
    OK = "ok"
    RESTATEMENT_OR_REVISION = "restatement_or_revision"


YTD_SPANS = (
    PeriodSpan.Q1,
    PeriodSpan.Q1_Q2,
    PeriodSpan.Q1_Q3,
    PeriodSpan.FISCAL_YEAR,
)

SPAN_END_QUARTER = {
    PeriodSpan.Q1: 1,
    PeriodSpan.Q1_Q2: 2,
    PeriodSpan.Q1_Q3: 3,
    PeriodSpan.FISCAL_YEAR: 4,
}

GapReason = Literal["missing_ytd_span", "prior_ytd_span_missing"]


def expected_period_bounds(
    fiscal_year_ending: int,
    period_span: PeriodSpan,
    fiscal_quarter: int | None = None,
) -> tuple[date, date]:
    """Inclusive dates for a fiscal span. Life-to-date has no fiscal window."""

    if period_span is PeriodSpan.LIFE_TO_DATE:
        raise GrainError("life_to_date has no fiscal-year window")
    if period_span is PeriodSpan.Q1:
        return quarter_bounds(fiscal_year_ending, 1)
    if period_span is PeriodSpan.Q1_Q2:
        start, _ = quarter_bounds(fiscal_year_ending, 1)
        _, end = quarter_bounds(fiscal_year_ending, 2)
        return start, end
    if period_span is PeriodSpan.Q1_Q3:
        start, _ = quarter_bounds(fiscal_year_ending, 1)
        _, end = quarter_bounds(fiscal_year_ending, 3)
        return start, end
    if period_span in (PeriodSpan.FISCAL_YEAR, PeriodSpan.FORECAST_FISCAL_YEAR):
        return fiscal_year_bounds(fiscal_year_ending)
    if period_span is PeriodSpan.QUARTER:
        if fiscal_quarter is None:
            raise GrainError("a single-quarter span includes fiscal_quarter")
        return quarter_bounds(fiscal_year_ending, fiscal_quarter)
    raise GrainError(f"unsupported period span {period_span}")


class DisclosureMeasure(BaseModel):
    """One figure as printed, after scale normalization into `value`.

    Year-to-date spans leave `fiscal_quarter` empty. The span name is the
    period. A single quarter uses period_span `quarter` plus fiscal_quarter.
    """

    model_config = ConfigDict(extra="forbid")

    source_document_id: str
    source_class: SourceClass
    metric_code: str
    product_grain: ProductGrain
    platform_code: str
    region_code: str
    game_code: str | None = None
    fiscal_year_ending: int | None = None
    period_span: PeriodSpan
    fiscal_quarter: int | None = None
    period_start: date | None = None
    period_end: date
    as_of_date: date
    value: Decimal
    is_forecast: bool = False
    is_additive_flow: bool = True
    is_platform_aggregate: bool = False
    is_platform_component: bool = False
    parent_platform_code: str | None = None
    is_region_aggregate: bool = False
    sales_basis: str = "sell_in"

    @model_validator(mode="after")
    def enforce_grain(self) -> "DisclosureMeasure":
        if not self.source_document_id.strip():
            raise GrainError("source_document_id is required")
        self._check_forecast_flag()
        self._check_platform_flags()
        self._check_product_grain()
        self._check_region_flag()
        self._check_period()
        if self.as_of_date < self.period_end:
            raise GrainError("as_of_date must be on or after period_end")
        return self

    def _check_forecast_flag(self) -> None:
        forecast_span = self.period_span is PeriodSpan.FORECAST_FISCAL_YEAR
        if self.is_forecast != forecast_span:
            raise GrainError(
                "is_forecast is true only when period_span is forecast_fiscal_year"
            )

    def _check_platform_flags(self) -> None:
        if self.is_platform_aggregate and self.is_platform_component:
            raise GrainError("a platform row is an aggregate or a component")
        if self.is_platform_component and not self.parent_platform_code:
            raise GrainError("a component names its parent platform")
        if self.is_platform_aggregate and self.parent_platform_code:
            raise GrainError("an aggregate platform has no parent")
        if self.parent_platform_code and self.parent_platform_code == self.platform_code:
            raise GrainError("a platform parent is a different code")

    def _check_product_grain(self) -> None:
        if self.product_grain is ProductGrain.FINANCIAL_LINE:
            if self.platform_code != "CONSOLIDATED":
                raise GrainError("financial lines use platform_code CONSOLIDATED")
            if self.game_code is not None:
                raise GrainError("financial lines leave game_code empty")
            if self.sales_basis != "not_applicable":
                raise GrainError("financial lines use sales_basis not_applicable")
            return
        if self.sales_basis != "sell_in":
            raise GrainError("unit sales use sales_basis sell_in")
        if self.platform_code == "CONSOLIDATED":
            raise GrainError("CONSOLIDATED is reserved for financial lines")
        if self.product_grain is ProductGrain.SOFTWARE_TITLE and not self.game_code:
            raise GrainError("a software title row includes game_code")
        if self.product_grain is not ProductGrain.SOFTWARE_TITLE and self.game_code:
            raise GrainError("hardware and software totals leave game_code empty")

    def _check_region_flag(self) -> None:
        if self.region_code == "GLOBAL" and not self.is_region_aggregate:
            raise GrainError("GLOBAL is an aggregate region and is marked as one")

    def _check_period(self) -> None:
        if self.period_span is PeriodSpan.LIFE_TO_DATE:
            if (
                self.fiscal_year_ending is not None
                or self.fiscal_quarter is not None
                or self.period_start is not None
            ):
                raise GrainError(
                    "life_to_date stores the as-of date in period_end and leaves "
                    "fiscal_year_ending, fiscal_quarter, and period_start empty"
                )
            return
        if self.fiscal_year_ending is None or self.period_start is None:
            raise GrainError("this span includes a fiscal year and a period start")
        if self.period_span in YTD_SPANS or self.period_span is PeriodSpan.FORECAST_FISCAL_YEAR:
            if self.fiscal_quarter is not None:
                raise GrainError(
                    "year-to-date and forecast spans leave fiscal_quarter empty. "
                    "The span name is the period."
                )
        elif self.period_span is PeriodSpan.QUARTER:
            if self.fiscal_quarter not in (1, 2, 3, 4):
                raise GrainError("a single-quarter span includes fiscal_quarter 1, 2, 3, or 4")
        expected_start, expected_end = expected_period_bounds(
            self.fiscal_year_ending,
            self.period_span,
            self.fiscal_quarter,
        )
        if (self.period_start, self.period_end) != (expected_start, expected_end):
            raise GrainError(
                f"{self.period_span.value} for FY3/{self.fiscal_year_ending} "
                f"covers {expected_start.isoformat()} through {expected_end.isoformat()}"
            )


class DerivedQuarter(BaseModel):
    """One fiscal quarter produced from year-to-date disclosures."""

    model_config = ConfigDict(extra="forbid")

    fiscal_year_ending: int
    fiscal_quarter: int
    metric_code: str
    product_grain: ProductGrain
    platform_code: str
    region_code: str
    game_code: str | None
    source_class: SourceClass
    incremental_value: Decimal
    opening_ytd_value: Decimal
    closing_ytd_value: Decimal
    derivation_method: Literal["ytd_equals_quarter", "difference_of_ytd"]
    is_as_disclosed: bool
    quality_flag: QualityFlag
    closing_source_document_id: str
    opening_source_document_id: str | None


class DerivationGap(BaseModel):
    """A quarter that the year-to-date series cannot support."""

    model_config = ConfigDict(extra="forbid")

    fiscal_year_ending: int
    fiscal_quarter: int
    metric_code: str
    product_grain: ProductGrain
    platform_code: str
    region_code: str
    game_code: str | None
    source_class: SourceClass
    reason: GapReason


class DerivationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quarters: list[DerivedQuarter]
    gaps: list[DerivationGap]


def _group_key(row: DisclosureMeasure) -> tuple:
    return (
        row.source_class,
        row.fiscal_year_ending,
        row.metric_code,
        row.product_grain,
        row.platform_code,
        row.region_code,
        row.game_code or "",
    )


def _latest(rows: list[DisclosureMeasure]) -> tuple[DisclosureMeasure, bool]:
    ranked = sorted(rows, key=lambda row: (row.as_of_date, row.source_document_id))
    return ranked[-1], len({row.value for row in rows}) > 1


def _require_derivable_ytd(rows: list[DisclosureMeasure]) -> None:
    classes = {row.source_class for row in rows}
    if len(classes) != 1:
        raise ProvenanceError("derive one source class at a time")
    for row in rows:
        if row.is_forecast or row.period_span is PeriodSpan.FORECAST_FISCAL_YEAR:
            raise GrainError("forecast rows stay on the disclosure grain")
        if row.period_span is PeriodSpan.LIFE_TO_DATE:
            raise GrainError("life-to-date rows stay on the disclosure grain")
        if row.period_span is PeriodSpan.QUARTER:
            raise GrainError(
                "period_span quarter is a single-quarter disclosure. "
                "The year-to-date derivation accepts q1, q1_q2, q1_q3, and fiscal_year."
            )
        if row.period_span not in SPAN_END_QUARTER:
            raise GrainError(f"unsupported span {row.period_span.value}")
        if not row.is_additive_flow:
            raise GrainError(f"{row.metric_code} is a stock and stays on the disclosure grain")


def derive_ytd_incremental(rows: list[DisclosureMeasure]) -> DerivationResult:
    """Derive quarters by subtracting adjacent year-to-date totals.

    Q1's year-to-date total is the first quarter. Later quarters require the
    immediately preceding span: H1 minus Q1, nine months minus H1, and the
    fiscal year minus nine months. Missing spans are returned as gaps.
    A negative difference is kept and flagged as a revision.
    """

    if not rows:
        return DerivationResult(quarters=[], gaps=[])
    _require_derivable_ytd(rows)

    grouped: dict[tuple, list[DisclosureMeasure]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)

    quarters: list[DerivedQuarter] = []
    gaps: list[DerivationGap] = []
    for key in sorted(grouped, key=lambda item: tuple(str(part) for part in item)):
        chosen, revised = _collapse_spans(grouped[key])
        sample = chosen[min(chosen)]
        for quarter in (1, 2, 3, 4):
            if quarter not in chosen:
                gaps.append(_gap(sample, quarter, "missing_ytd_span"))
                continue
            current = chosen[quarter]
            if quarter == 1:
                quarters.append(_quarter_from_identity(current, revised[quarter]))
                continue
            if quarter - 1 not in chosen:
                gaps.append(_gap(sample, quarter, "prior_ytd_span_missing"))
                continue
            prior = chosen[quarter - 1]
            quarters.append(
                _quarter_from_difference(
                    current,
                    prior,
                    revised[quarter] or revised[quarter - 1],
                )
            )
    return DerivationResult(quarters=quarters, gaps=gaps)


def derive_reported_incremental(rows: list[DisclosureMeasure]) -> DerivationResult:
    """Same derivation, restricted to official IR actuals."""

    for row in rows:
        assert_reported_mart_source(row.source_class)
    return derive_ytd_incremental(rows)


def _collapse_spans(
    rows: list[DisclosureMeasure],
) -> tuple[dict[int, DisclosureMeasure], dict[int, bool]]:
    by_span: dict[PeriodSpan, list[DisclosureMeasure]] = defaultdict(list)
    for row in rows:
        by_span[row.period_span].append(row)
    chosen: dict[int, DisclosureMeasure] = {}
    revised: dict[int, bool] = {}
    for span, span_rows in by_span.items():
        quarter = SPAN_END_QUARTER[span]
        pick, changed = _latest(span_rows)
        chosen[quarter] = pick
        revised[quarter] = changed
    return chosen, revised


def _gap(sample: DisclosureMeasure, quarter: int, reason: GapReason) -> DerivationGap:
    return DerivationGap(
        fiscal_year_ending=sample.fiscal_year_ending,  # type: ignore[arg-type]
        fiscal_quarter=quarter,
        metric_code=sample.metric_code,
        product_grain=sample.product_grain,
        platform_code=sample.platform_code,
        region_code=sample.region_code,
        game_code=sample.game_code,
        source_class=sample.source_class,
        reason=reason,
    )


def _quarter_from_identity(current: DisclosureMeasure, revised: bool) -> DerivedQuarter:
    return DerivedQuarter(
        fiscal_year_ending=current.fiscal_year_ending,  # type: ignore[arg-type]
        fiscal_quarter=1,
        metric_code=current.metric_code,
        product_grain=current.product_grain,
        platform_code=current.platform_code,
        region_code=current.region_code,
        game_code=current.game_code,
        source_class=current.source_class,
        incremental_value=current.value,
        opening_ytd_value=Decimal("0"),
        closing_ytd_value=current.value,
        derivation_method="ytd_equals_quarter",
        is_as_disclosed=True,
        quality_flag=QualityFlag.RESTATEMENT_OR_REVISION if revised else QualityFlag.OK,
        closing_source_document_id=current.source_document_id,
        opening_source_document_id=None,
    )


def _quarter_from_difference(
    current: DisclosureMeasure,
    prior: DisclosureMeasure,
    revised: bool,
) -> DerivedQuarter:
    delta = current.value - prior.value
    flag = QualityFlag.RESTATEMENT_OR_REVISION if revised or delta < 0 else QualityFlag.OK
    return DerivedQuarter(
        fiscal_year_ending=current.fiscal_year_ending,  # type: ignore[arg-type]
        fiscal_quarter=SPAN_END_QUARTER[current.period_span],
        metric_code=current.metric_code,
        product_grain=current.product_grain,
        platform_code=current.platform_code,
        region_code=current.region_code,
        game_code=current.game_code,
        source_class=current.source_class,
        incremental_value=delta,
        opening_ytd_value=prior.value,
        closing_ytd_value=current.value,
        derivation_method="difference_of_ytd",
        is_as_disclosed=False,
        quality_flag=flag,
        closing_source_document_id=current.source_document_id,
        opening_source_document_id=prior.source_document_id,
    )
