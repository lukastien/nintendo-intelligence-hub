"""Warehouse tests.

Rolled-back rows use fiscal year 2099 and the platform code SYN_PLATFORM.
They exercise the SQL grain rules and are not Nintendo disclosures.
"""

from datetime import date
from decimal import Decimal

import pytest

from nih.periods import (
    PeriodSpan,
    ProductGrain,
    derive_reported_incremental,
    expected_period_bounds,
)
from tests.factories import measure, ytd
from warehouse.audit import database_reachable

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def warehouse():
    if not database_reachable():
        pytest.skip("PostgreSQL is not running")
    import subprocess

    from nih.config import project_root
    from warehouse.load import initialize_database

    dbt = _dbt_executable()
    if dbt is None:
        pytest.skip("dbt is not installed")
    summary = initialize_database()
    subprocess.run(
        [
            dbt,
            "build",
            "--project-dir",
            "transformations/dbt",
            "--profiles-dir",
            "transformations/dbt",
        ],
        cwd=project_root(),
        check=True,
    )
    return summary


def _dbt_executable() -> str | None:
    import shutil
    import sys
    from pathlib import Path

    candidate = Path(sys.prefix) / "bin" / "dbt"
    if candidate.exists():
        return str(candidate)
    return shutil.which("dbt")


def test_bootstrap_does_not_insert_official_measures(warehouse):
    from warehouse.load import initialize_database

    again = initialize_database()
    assert again["official_unit_rows"] == warehouse["official_unit_rows"]
    assert again["official_financial_rows"] == warehouse["official_financial_rows"]
    assert warehouse["simulated_rows"] == 48
    assert warehouse["platforms"] == 24
    assert warehouse["regions"] == 6
    assert warehouse["dates"] > 4000


def test_sql_period_bounds_match_the_python_calendar(warehouse):
    from nih.db import connect

    spans = [
        (PeriodSpan.Q1, None),
        (PeriodSpan.Q1_Q2, None),
        (PeriodSpan.Q1_Q3, None),
        (PeriodSpan.FISCAL_YEAR, None),
        (PeriodSpan.FORECAST_FISCAL_YEAR, None),
        (PeriodSpan.QUARTER, 1),
        (PeriodSpan.QUARTER, 2),
        (PeriodSpan.QUARTER, 3),
        (PeriodSpan.QUARTER, 4),
    ]
    with connect() as connection:
        with connection.cursor() as cursor:
            for year in (2020, 2026, 2099):
                for span, quarter in spans:
                    start, end = expected_period_bounds(year, span, quarter)
                    cursor.execute(
                        "select ref.period_bounds_ok(%s, %s, %s, %s, %s)",
                        (year, span.value, quarter, start, end),
                    )
                    assert cursor.fetchone()[0] is True
            cursor.execute(
                "select ref.period_bounds_ok(%s, %s, %s, %s, %s)",
                (2026, "quarter", 3, date(2025, 4, 1), date(2025, 12, 31)),
            )
            assert cursor.fetchone()[0] is False
            cursor.execute(
                "select ref.period_bounds_ok(%s, %s, %s, %s, %s)",
                (None, "life_to_date", None, None, date(2026, 6, 30)),
            )
            assert cursor.fetchone()[0] is True


def test_sql_incremental_view_matches_the_python_derivation(warehouse):
    import psycopg

    from nih.db import connect

    with connect() as connection:
        with connection.transaction(force_rollback=True):
            _insert_unit(
                connection,
                document_id="synthetic_test_q1",
                span="q1",
                start=date(2098, 4, 1),
                end=date(2098, 6, 30),
                value=Decimal("1000"),
            )
            _insert_unit(
                connection,
                document_id="synthetic_test_h1",
                span="q1_q2",
                start=date(2098, 4, 1),
                end=date(2098, 9, 30),
                value=Decimal("1400"),
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select fiscal_quarter, incremental_value, derivation_method,
                           quality_flag, is_as_disclosed
                    from mart_reported.unit_sales_incremental_quarter
                    where platform_code = 'SYN_PLATFORM'
                    order by fiscal_quarter
                    """
                )
                rows = cursor.fetchall()
            expected = derive_reported_incremental(
                [
                    ytd(PeriodSpan.Q1, "1000", "synthetic_test_q1"),
                    ytd(PeriodSpan.Q1_Q2, "1400", "synthetic_test_h1"),
                ]
            )
            expected_quarters = [row for row in expected.quarters if row.fiscal_quarter in (1, 2)]
            assert [row[0] for row in rows] == [1, 2]
            assert [Decimal(row[1]) for row in rows] == [Decimal("1000"), Decimal("400")]
            assert [row[2] for row in rows] == [item.derivation_method for item in expected_quarters]
            assert [row[3] for row in rows] == [item.quality_flag.value for item in expected_quarters]
            assert [row[4] for row in rows] == [True, False]
            with pytest.raises(psycopg.Error):
                with connection.transaction():
                    _insert_unit(
                        connection,
                        document_id="synthetic_test_bad_quarter",
                        span="q1_q3",
                        start=date(2098, 4, 1),
                        end=date(2098, 12, 31),
                        value=Decimal("1800"),
                        fiscal_quarter=3,
                    )


def test_one_document_can_store_two_fiscal_years(warehouse):
    import psycopg

    from nih.db import connect

    with connect() as connection:
        with connection.transaction(force_rollback=True):
            for year in (2098, 2099):
                start, end = expected_period_bounds(year, PeriodSpan.FISCAL_YEAR)
                _insert_unit(
                    connection,
                    document_id="synthetic_two_years",
                    span="fiscal_year",
                    start=start,
                    end=end,
                    value=Decimal("1000"),
                    fiscal_year=year,
                )
                _insert_financial(
                    connection,
                    document_id="synthetic_two_years",
                    span="fiscal_year",
                    start=start,
                    end=end,
                    printed=Decimal("10"),
                    yen=Decimal("10000000"),
                    fiscal_year=year,
                )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select count(*)
                    from raw_official.unit_sales_disclosure
                    where source_document_id = 'synthetic_two_years'
                    """
                )
                assert cursor.fetchone()[0] == 2
                cursor.execute(
                    """
                    select count(*)
                    from raw_official.financial_line
                    where source_document_id = 'synthetic_two_years'
                    """
                )
                assert cursor.fetchone()[0] == 2
            with pytest.raises(psycopg.Error):
                with connection.transaction():
                    _insert_unit(
                        connection,
                        document_id="synthetic_two_years",
                        span="life_to_date",
                        start=None,
                        end=date(2099, 3, 31),
                        value=Decimal("1000"),
                        fiscal_year=None,
                    )
                    _insert_unit(
                        connection,
                        document_id="synthetic_two_years",
                        span="life_to_date",
                        start=None,
                        end=date(2099, 3, 31),
                        value=Decimal("1100"),
                        fiscal_year=None,
                    )


def test_as_of_date_must_be_on_or_after_period_end(warehouse):
    import psycopg

    from nih.db import connect

    start, end = expected_period_bounds(2099, PeriodSpan.Q1)
    with connect() as connection:
        with connection.transaction(force_rollback=True):
            with pytest.raises(psycopg.Error):
                with connection.transaction():
                    _insert_unit(
                        connection,
                        document_id="synthetic_early_as_of",
                        span="q1",
                        start=start,
                        end=end,
                        value=Decimal("1000"),
                        as_of=date(2098, 6, 1),
                    )
            with pytest.raises(psycopg.Error):
                with connection.transaction():
                    _insert_financial(
                        connection,
                        document_id="synthetic_early_as_of",
                        span="q1",
                        start=start,
                        end=end,
                        printed=Decimal("10"),
                        yen=Decimal("10000000"),
                        as_of=date(2098, 6, 1),
                    )


def test_printed_scale_must_match_the_normalized_amount(warehouse):
    import psycopg

    from nih.db import connect

    start, end = expected_period_bounds(2099, PeriodSpan.Q1)
    with connect() as connection:
        with connection.transaction(force_rollback=True):
            with pytest.raises(psycopg.Error):
                with connection.transaction():
                    _insert_unit(
                        connection,
                        document_id="synthetic_bad_scale",
                        span="q1",
                        start=start,
                        end=end,
                        value=Decimal("1000"),
                        scale=10000,
                    )
            with pytest.raises(psycopg.Error):
                with connection.transaction():
                    _insert_financial(
                        connection,
                        document_id="synthetic_bad_scale",
                        span="q1",
                        start=start,
                        end=end,
                        printed=Decimal("10"),
                        yen=Decimal("10"),
                    )


def test_financial_incremental_view_matches_python_and_skips_stocks(warehouse):
    from nih.db import connect

    q1_start, q1_end = expected_period_bounds(2099, PeriodSpan.Q1)
    h1_start, h1_end = expected_period_bounds(2099, PeriodSpan.Q1_Q2)
    additive = [
        _financial_measure("fin_q1", PeriodSpan.Q1, "10000000"),
        _financial_measure("fin_h1", PeriodSpan.Q1_Q2, "14000000"),
    ]
    with connect() as connection:
        with connection.transaction(force_rollback=True):
            _insert_financial(
                connection,
                document_id="fin_q1",
                span="q1",
                start=q1_start,
                end=q1_end,
                printed=Decimal("10"),
                yen=Decimal("10000000"),
            )
            _insert_financial(
                connection,
                document_id="fin_h1",
                span="q1_q2",
                start=h1_start,
                end=h1_end,
                printed=Decimal("14"),
                yen=Decimal("14000000"),
            )
            _insert_financial(
                connection,
                document_id="zzz_row_says_stock",
                span="q1",
                start=q1_start,
                end=q1_end,
                printed=Decimal("999"),
                yen=Decimal("999000000"),
                additive=False,
            )
            _insert_financial(
                connection,
                document_id="assets_row_says_flow",
                span="q1",
                start=q1_start,
                end=q1_end,
                printed=Decimal("10"),
                yen=Decimal("10000000"),
                metric="total_assets_jpy",
                additive=True,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select fiscal_quarter, incremental_value, derivation_method,
                           quality_flag, is_as_disclosed
                    from mart_reported.financial_flow_incremental_quarter
                    where metric_code = 'net_sales_jpy'
                      and fiscal_year_ending = 2099
                    order by fiscal_quarter
                    """
                )
                rows = cursor.fetchall()
                cursor.execute(
                    """
                    select count(*)
                    from mart_reported.financial_flow_incremental_quarter
                    where metric_code = 'total_assets_jpy'
                       or closing_source_document_id = 'zzz_row_says_stock'
                    """
                )
                excluded = cursor.fetchone()[0]
                cursor.execute(
                    """
                    select source_document_id
                    from mart_reported.financial_line_as_disclosed
                    where source_document_id in ('zzz_row_says_stock', 'assets_row_says_flow')
                    order by source_document_id
                    """
                )
                disclosed = [row[0] for row in cursor.fetchall()]
            expected = derive_reported_incremental(additive)
            expected_quarters = [row for row in expected.quarters if row.fiscal_quarter in (1, 2)]
            assert [row[0] for row in rows] == [1, 2]
            assert [Decimal(row[1]) for row in rows] == [Decimal("10000000"), Decimal("4000000")]
            assert [row[2] for row in rows] == [item.derivation_method for item in expected_quarters]
            assert [row[3] for row in rows] == [item.quality_flag.value for item in expected_quarters]
            assert [row[4] for row in rows] == [True, False]
            assert excluded == 0
            assert disclosed == ["assets_row_says_flow", "zzz_row_says_stock"]


def test_simulated_rows_use_synthetic_labels(warehouse):
    from nih.db import connect

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select count(*)
                from raw_simulated.weekly_sell_through
                where series_name like 'synthetic_%'
                  and sku_code like 'SYN_%'
                  and region_code like 'SIM_%'
                """
            )
            assert cursor.fetchone()[0] == 48
            cursor.execute(
                """
                select count(*)
                from mart_simulated.weekly_sell_through
                where source_class = 'simulated_operational'
                """
            )
            assert cursor.fetchone()[0] == 48
            cursor.execute(
                """
                select count(*)
                from raw_official.unit_sales_disclosure
                where platform_code = 'SYN_PLATFORM'
                """
            )
            assert cursor.fetchone()[0] == 0


def _insert_unit(
    connection,
    document_id,
    span,
    start,
    end,
    value,
    fiscal_quarter=None,
    fiscal_year=2099,
    as_of=None,
    scale=1,
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into raw_official.unit_sales_disclosure (
                source_document_id, source_class, metric_code, product_grain,
                platform_code, is_platform_aggregate, is_platform_component,
                region_code, is_region_aggregate, fiscal_year_ending, period_span,
                fiscal_quarter, period_start, period_end, as_of_date, value_units,
                source_unit_scale, source_value_as_printed, is_forecast,
                is_additive_flow, sales_basis, definition_note
            ) values (
                %s, 'official_ir', 'hw_units_sell_in', 'hardware',
                'SYN_PLATFORM', false, false,
                'SYN_REGION', false, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, false,
                true, 'sell_in', 'Synthetic transaction fixture rolled back by the test.'
            )
            """,
            (
                document_id,
                fiscal_year,
                span,
                fiscal_quarter,
                start,
                end,
                end if as_of is None else as_of,
                value,
                scale,
                value,
            ),
        )


def _insert_financial(
    connection,
    document_id,
    span,
    start,
    end,
    printed,
    yen,
    fiscal_year=2099,
    metric="net_sales_jpy",
    additive=True,
    scale="millions",
    as_of=None,
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into raw_official.financial_line (
                source_document_id, source_class, metric_code, region_code,
                is_region_aggregate, fiscal_year_ending, period_span, fiscal_quarter,
                period_start, period_end, as_of_date, amount_as_printed, printed_scale,
                amount_yen, is_forecast, is_additive_flow, definition_note
            ) values (
                %s, 'official_ir', %s, 'GLOBAL',
                true, %s, %s, null,
                %s, %s, %s, %s, %s,
                %s, false, %s, 'Synthetic transaction fixture rolled back by the test.'
            )
            """,
            (
                document_id,
                metric,
                fiscal_year,
                span,
                start,
                end,
                end if as_of is None else as_of,
                printed,
                scale,
                yen,
                additive,
            ),
        )


def _financial_measure(document_id: str, span: PeriodSpan, value: str):
    start, end = expected_period_bounds(2099, span)
    return measure(
        source_document_id=document_id,
        metric_code="net_sales_jpy",
        product_grain=ProductGrain.FINANCIAL_LINE,
        platform_code="CONSOLIDATED",
        region_code="GLOBAL",
        is_region_aggregate=True,
        sales_basis="not_applicable",
        period_span=span,
        period_start=start,
        period_end=end,
        as_of_date=end,
        value=Decimal(value),
    )
