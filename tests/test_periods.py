from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from pydantic import ValidationError

from nih.errors import GrainError, ProvenanceError
from nih.periods import (
    PeriodSpan,
    ProductGrain,
    QualityFlag,
    derive_reported_incremental,
    expected_period_bounds,
)
from nih.provenance import SourceClass
from tests.factories import measure, ytd
from transformations.incremental import disclosures_to_incremental


def test_q1_year_to_date_is_the_first_quarter():
    result = derive_reported_incremental([ytd(PeriodSpan.Q1, "1000", "synthetic_q1")])
    assert len(result.quarters) == 1
    quarter = result.quarters[0]
    assert quarter.fiscal_quarter == 1
    assert quarter.incremental_value == Decimal("1000")
    assert quarter.derivation_method == "ytd_equals_quarter"
    assert quarter.is_as_disclosed is True
    assert {gap.fiscal_quarter for gap in result.gaps} == {2, 3, 4}


def test_half_year_minus_q1_is_the_second_quarter():
    result = derive_reported_incremental(
        [
            ytd(PeriodSpan.Q1, "1000", "synthetic_q1"),
            ytd(PeriodSpan.Q1_Q2, "1400", "synthetic_h1"),
        ]
    )
    derived = {row.fiscal_quarter: row for row in result.quarters}
    assert derived[2].incremental_value == Decimal("400")
    assert derived[2].opening_ytd_value == Decimal("1000")
    assert derived[2].closing_ytd_value == Decimal("1400")
    assert derived[2].derivation_method == "difference_of_ytd"
    assert derived[2].is_as_disclosed is False
    assert derived[2].quality_flag is QualityFlag.OK


def test_a_missing_half_blocks_q3_and_leaves_q4_derivable():
    result = derive_reported_incremental(
        [
            ytd(PeriodSpan.Q1, "1000", "synthetic_q1"),
            ytd(PeriodSpan.Q1_Q3, "1800", "synthetic_nine_months"),
            ytd(PeriodSpan.FISCAL_YEAR, "2000", "synthetic_fy"),
        ]
    )
    derived = {row.fiscal_quarter: row for row in result.quarters}
    assert sorted(derived) == [1, 4]
    assert derived[4].incremental_value == Decimal("200")
    assert derived[4].opening_ytd_value == Decimal("1800")
    reasons = {gap.fiscal_quarter: gap.reason for gap in result.gaps}
    assert reasons[2] == "missing_ytd_span"
    assert reasons[3] == "prior_ytd_span_missing"
    assert 4 not in reasons


def test_negative_difference_is_kept_and_flagged():
    result = derive_reported_incremental(
        [
            ytd(PeriodSpan.Q1, "500", "synthetic_q1"),
            ytd(PeriodSpan.Q1_Q2, "400", "synthetic_h1"),
        ]
    )
    quarter = next(row for row in result.quarters if row.fiscal_quarter == 2)
    assert quarter.incremental_value == Decimal("-100")
    assert quarter.quality_flag is QualityFlag.RESTATEMENT_OR_REVISION


def test_revised_duplicate_uses_the_later_document():
    start, end = expected_period_bounds(2099, PeriodSpan.Q1)
    first = measure(
        source_document_id="synthetic_early",
        period_start=start,
        period_end=end,
        as_of_date=date(2098, 7, 1),
        value=Decimal("1000"),
    )
    revised = measure(
        source_document_id="synthetic_revised",
        period_start=start,
        period_end=end,
        as_of_date=date(2098, 8, 1),
        value=Decimal("1100"),
    )
    result = derive_reported_incremental([first, revised])
    quarter = result.quarters[0]
    assert quarter.incremental_value == Decimal("1100")
    assert quarter.closing_source_document_id == "synthetic_revised"
    assert quarter.quality_flag is QualityFlag.RESTATEMENT_OR_REVISION


def test_as_of_date_before_period_end_is_rejected():
    with pytest.raises(ValidationError, match="as_of_date must be on or after period_end"):
        measure(as_of_date=date(2098, 6, 1))


def test_nine_month_dates_cannot_be_labeled_as_the_third_quarter():
    with pytest.raises(ValidationError, match="2098-10-01 through 2098-12-31"):
        measure(
            period_span=PeriodSpan.QUARTER,
            fiscal_quarter=3,
            period_start=date(2098, 4, 1),
            period_end=date(2098, 12, 31),
            as_of_date=date(2098, 12, 31),
        )


def test_single_third_quarter_is_valid_and_stays_out_of_the_ytd_derivation():
    start, end = expected_period_bounds(2099, PeriodSpan.QUARTER, 3)
    row = measure(
        period_span=PeriodSpan.QUARTER,
        fiscal_quarter=3,
        period_start=start,
        period_end=end,
        as_of_date=end,
    )
    assert row.period_start == date(2098, 10, 1)
    with pytest.raises(GrainError, match="single-quarter"):
        derive_reported_incremental([row])


def test_life_to_date_and_forecasts_stay_on_the_disclosure_grain():
    lifetime = measure(
        period_span=PeriodSpan.LIFE_TO_DATE,
        fiscal_year_ending=None,
        fiscal_quarter=None,
        period_start=None,
        period_end=date(2098, 12, 31),
        as_of_date=date(2098, 12, 31),
        source_document_id="synthetic_lifetime",
    )
    with pytest.raises(GrainError, match="life-to-date"):
        derive_reported_incremental([lifetime])

    start, end = expected_period_bounds(2099, PeriodSpan.FORECAST_FISCAL_YEAR)
    with pytest.raises(GrainError, match="forecast"):
        derive_reported_incremental(
            [
                measure(
                    period_span=PeriodSpan.FORECAST_FISCAL_YEAR,
                    is_forecast=True,
                    period_start=start,
                    period_end=end,
                    as_of_date=end,
                    source_document_id="synthetic_forecast",
                )
            ]
        )


def test_balance_sheet_stock_is_rejected():
    row = ytd(PeriodSpan.Q1, "1000", "synthetic_assets")
    stock = row.model_copy(
        update={"metric_code": "total_assets_jpy", "is_additive_flow": False, "product_grain": ProductGrain.FINANCIAL_LINE, "platform_code": "CONSOLIDATED", "sales_basis": "not_applicable"}
    )
    with pytest.raises(GrainError, match="stock"):
        derive_reported_incremental([stock])


def test_simulated_rows_cannot_enter_the_reported_derivation():
    row = ytd(PeriodSpan.Q1, "1000", "synthetic_q1").model_copy(
        update={"source_class": SourceClass.SIMULATED_OPERATIONAL}
    )
    with pytest.raises(ProvenanceError):
        derive_reported_incremental([row])


def test_year_to_date_span_rejects_a_stored_fiscal_quarter():
    start, end = expected_period_bounds(2099, PeriodSpan.Q1_Q3)
    with pytest.raises(ValidationError, match="fiscal_quarter"):
        measure(
            period_span=PeriodSpan.Q1_Q3,
            fiscal_quarter=3,
            period_start=start,
            period_end=end,
            as_of_date=end,
            value=Decimal("1800"),
            source_document_id="synthetic_nine_months",
        )


def test_dataframe_wrapper_returns_derived_quarters():
    rows = [
        ytd(PeriodSpan.Q1, "1000", "synthetic_q1").model_dump(),
        ytd(PeriodSpan.Q1_Q2, "1400", "synthetic_h1").model_dump(),
    ]
    frame = disclosures_to_incremental(pd.DataFrame(rows))
    assert sorted(frame["fiscal_quarter"]) == [1, 2]
    assert set(frame["source_class"]) == {SourceClass.OFFICIAL_IR}
