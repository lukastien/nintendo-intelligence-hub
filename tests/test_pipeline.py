"""Pipeline orchestration tests.

Warehouse scenarios use a fiscal-year-2099 fixture document and delete it
before the test returns. They do not download Nintendo.
"""

from datetime import date
from decimal import Decimal

import pytest

from ingestion.http import FetchError
from ingestion.records import SourceOutcome
from ingestion.warehouse import classify_row_changes
from nih.pipeline import (
    LOCK_KEY,
    expected_as_of,
    freshness_findings,
    mandatory_problems,
    mart_problems,
    optional_warnings,
    pipeline_history,
    run_pipeline,
)
from warehouse.audit import database_reachable

FIXTURE_DOCUMENT = "nintendo_dedicated_units_2099-06-30"
DEDICATED_HTML = """
<div class="sinf_date">( As of June 30, 2099 )</div>
<p class="hard_name">Nintendo Switch 2</p>
<p class="data">
  <span class="fs-g">Hardware:</span><span class="num">1.5</span><span class="unit">million pcs.</span>
  <span class="fs-g">Software:</span><span class="num">2.25</span><span class="unit">million pcs.</span>
</p>
<img alt="Wii" src="a.png">
<img alt="Hardware: 3 million pcs. / Software: 4 million pcs." src="b.png">
"""
REVISED_HTML = DEDICATED_HTML.replace(">1.5<", ">1.6<")


def test_classify_row_changes_counts_each_kind_of_difference():
    existing = {("unit", "a"): Decimal("1"), ("unit", "b"): Decimal("2"), ("unit", "c"): Decimal("3")}
    incoming = {("unit", "b"): Decimal("2"), ("unit", "c"): Decimal("9"), ("unit", "d"): Decimal("4")}
    assert classify_row_changes(existing, incoming) == (1, 1, 1, 1)


def test_annual_history_is_current_on_its_publication_schedule():
    today = date(2026, 10, 20)
    assert expected_as_of(today, "annual_historical") == date(2026, 3, 31)
    assert expected_as_of(today, "quarterly_page") == date(2026, 6, 30)
    documents = [
        ("nintendo_sales_transition_20260331", date(2026, 3, 31)),
        ("nintendo_income_transition_20260331", date(2026, 3, 31)),
        ("nintendo_dedicated_units_2026-06-30", date(2026, 6, 30)),
        ("nintendo_top_titles_3ds_2026-03-31", date(2026, 3, 31)),
    ]
    assert freshness_findings(documents, today) == []
    overdue = [("nintendo_sales_transition_20250331", date(2025, 3, 31))]
    assert any("annual historical workbook is overdue" in item for item in freshness_findings(overdue, today))


def test_mart_problems_ignore_empty_quarterly_marts():
    counts = {
        "mart_annual_platform_performance": 10,
        "mart_hardware_software_trends": 4,
        "mart_lifetime_platform_sales": 2,
        "mart_regional_performance": 8,
        "mart_financial_performance": 4,
        "unit_sales_incremental_quarter": 0,
        "financial_flow_incremental_quarter": 0,
        "weekly_sell_through": 48,
        "official_unit_rows": 10,
        "official_financial_rows": 4,
        "simulated_rows": 48,
        "reported_non_official": 0,
        "simulated_non_simulated": 0,
    }
    assert mart_problems(counts) == []
    counts["mart_annual_platform_performance"] = 0
    assert any("mart_annual_platform_performance" in item for item in mart_problems(counts))
    del counts["unit_sales_incremental_quarter"]
    assert any("unit_sales_incremental_quarter" in item for item in mart_problems(counts))


def test_optional_sources_are_warnings_and_mandatory_failures_stay_separate():
    outcomes = [
        SourceOutcome(
            "nintendo_dedicated_unit_sales",
            "official_ir",
            "unavailable",
            0,
            0,
            0,
            "offline",
        ),
        SourceOutcome(
            "igdb_game_metadata",
            "public_reference",
            "unavailable",
            0,
            0,
            0,
            "credentials are not set",
        ),
    ]
    problems = mandatory_problems(outcomes)
    warnings = optional_warnings(outcomes)
    assert any("nintendo_dedicated_unit_sales" in item for item in problems)
    assert all("igdb_game_metadata" not in item for item in problems)
    assert any("igdb_game_metadata" in item for item in warnings)


@pytest.mark.integration
def test_repeat_and_correction_do_not_duplicate_official_rows(tmp_path):
    _require_database()
    _delete_fixture()
    before = _counts()
    try:
        first = _run_dedicated(tmp_path, DEDICATED_HTML)
        assert first.ok
        assert first.records_inserted == 4
        assert first.records_unchanged == 0
        assert _fixture_rows() == 4
        assert _counts()["units"] == before["units"] + 4
        assert _counts()["simulated"] == before["simulated"]

        second = _run_dedicated(tmp_path, DEDICATED_HTML)
        assert second.ok
        assert second.records_inserted == 0
        assert second.records_updated == 0
        assert second.records_unchanged == 4
        assert _fixture_rows() == 4
        assert _counts()["units"] == before["units"] + 4

        revised = _run_dedicated(tmp_path, REVISED_HTML)
        assert revised.ok
        assert revised.records_inserted == 0
        assert revised.records_updated == 1
        assert revised.records_unchanged == 3
        assert _fixture_rows() == 4
        assert _switch2_hardware() == Decimal("1600000")
        assert _counts()["units"] == before["units"] + 4
        assert _counts()["financial"] == before["financial"]
    finally:
        _delete_fixture()
    assert _counts() == before


@pytest.mark.integration
def test_missing_and_malformed_sources_keep_validated_rows(tmp_path):
    _require_database()
    _delete_fixture()
    try:
        loaded = _run_dedicated(tmp_path, DEDICATED_HTML)
        assert loaded.ok
        before = _counts()

        def offline(_url: str) -> bytes:
            raise FetchError("offline")

        missing = run_pipeline(
            ["nintendo_dedicated_unit_sales"],
            fetcher=offline,
            output_root=tmp_path / "missing",
            skip_dbt=True,
            verify_marts=False,
        )
        assert missing.exit_code == 1
        assert missing.status == "failed"
        assert "unavailable" in missing.error_message
        assert _fixture_rows() == 4
        assert _counts() == before

        malformed = run_pipeline(
            ["nintendo_dedicated_unit_sales"],
            fetcher=lambda _url: b"<html>no disclosure table</html>",
            output_root=tmp_path / "malformed",
            skip_dbt=True,
            verify_marts=False,
        )
        assert malformed.exit_code == 1
        assert malformed.status == "failed"
        assert _fixture_rows() == 4
        assert _counts() == before
        history = pipeline_history(limit=5)
        assert "failed" in history
    finally:
        _delete_fixture()


@pytest.mark.integration
def test_dbt_failure_is_recorded_without_removing_the_load(tmp_path):
    _require_database()
    _delete_fixture()
    try:
        failed = _run_dedicated(tmp_path, DEDICATED_HTML, dbt_status="failed")
        assert failed.status == "failed"
        assert failed.dbt_status == "failed"
        assert failed.records_inserted == 4
        assert _fixture_rows() == 4
        history = pipeline_history(limit=3)
        assert "failed" in history
        assert failed.run_id is not None
        assert failed.run_id in history
    finally:
        _delete_fixture()


@pytest.mark.integration
def test_a_second_pipeline_is_rejected_while_the_lock_is_held(tmp_path):
    _require_database()
    from nih.db import connect

    calls = {"count": 0}

    def fetcher(_url: str) -> bytes:
        calls["count"] += 1
        raise AssertionError("the busy run must not ingest")

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,))
            assert cursor.fetchone()[0] is True
        connection.commit()
        try:
            result = run_pipeline(
                ["nintendo_dedicated_unit_sales"],
                fetcher=fetcher,
                output_root=tmp_path,
                skip_dbt=True,
                verify_marts=False,
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
            connection.commit()
    assert result.exit_code == 2
    assert calls["count"] == 0
    assert "already executing" in result.error_message
    assert result.run_id is not None
    assert result.run_id in pipeline_history(limit=5)


def _require_database() -> None:
    if not database_reachable():
        pytest.skip("PostgreSQL is not running")


def _run_dedicated(tmp_path, html: str, dbt_status: str = "success"):
    def runner():
        from nih.pipeline import DbtResult

        if dbt_status != "success":
            return DbtResult(dbt_status, "dbt build failed in the test runner")
        return DbtResult("success", "dbt build succeeded")

    return run_pipeline(
        ["nintendo_dedicated_unit_sales"],
        fetcher=lambda _url: html.encode("utf-8"),
        output_root=tmp_path,
        dbt_runner=runner,
        skip_dbt=dbt_status == "success",
        verify_marts=False,
    )


def _counts() -> dict[str, int]:
    from nih.db import connect

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from raw_official.unit_sales_disclosure")
            units = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from raw_official.financial_line")
            financial = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from raw_simulated.weekly_sell_through")
            simulated = int(cursor.fetchone()[0])
    return {"units": units, "financial": financial, "simulated": simulated}


def _fixture_rows() -> int:
    from nih.db import connect

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select count(*)
                from raw_official.unit_sales_disclosure
                where source_document_id = %s
                """,
                (FIXTURE_DOCUMENT,),
            )
            return int(cursor.fetchone()[0])


def _switch2_hardware() -> Decimal:
    from nih.db import connect

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select value_units
                from raw_official.unit_sales_disclosure
                where source_document_id = %s
                  and platform_code = 'NS2'
                  and metric_code = 'hw_units_sell_in'
                """,
                (FIXTURE_DOCUMENT,),
            )
            return Decimal(cursor.fetchone()[0])


def _delete_fixture() -> None:
    from nih.db import connect

    with connect() as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from raw_official.unit_sales_disclosure where source_document_id = %s",
                    (FIXTURE_DOCUMENT,),
                )
                cursor.execute(
                    "delete from meta.source_document where source_document_id = %s",
                    (FIXTURE_DOCUMENT,),
                )
