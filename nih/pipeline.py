"""Orchestrate ingestion, warehouse checks, and dbt.

`pipeline run` is safe to repeat. An unavailable Nintendo source does not
delete rows already loaded for that document. Optional sources that are
not configured are warnings. Mandatory parse, audit, dbt, and mart failures
fail the run.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ingestion.pipeline import OFFICIAL_SOURCES, OPTIONAL_SOURCES, run_ingestion
from ingestion.records import SourceOutcome
from nih.config import Settings, load_settings, project_root
from nih.db import connect
from nih.errors import ConfigurationError, NihError
from warehouse.apply import split_sql

logger = logging.getLogger("nih.pipeline")

LOCK_KEY = 84020401
ANNUAL_PUBLICATION_LAG_DAYS = 90
QUARTERLY_PUBLICATION_LAG_DAYS = 45
UNIT_MARTS = (
    "mart_annual_platform_performance",
    "mart_hardware_software_trends",
    "mart_lifetime_platform_sales",
    "mart_regional_performance",
)
FINANCIAL_MARTS = ("mart_financial_performance",)
QUARTERLY_MARTS = (
    "unit_sales_incremental_quarter",
    "financial_flow_incremental_quarter",
)
REQUIRED_MARTS = UNIT_MARTS + FINANCIAL_MARTS + QUARTERLY_MARTS

DbtRunner = Callable[[], "DbtResult"]


class PipelineBusy(NihError):
    """Raised when another pipeline execution holds the advisory lock."""


@dataclass
class DbtResult:
    status: str
    message: str


@dataclass
class PipelineResult:
    run_id: str | None
    status: str
    ok: bool
    exit_code: int
    error_message: str = ""
    documents_processed: int = 0
    records_extracted: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    records_rejected: int = 0
    dbt_status: str = "not_run"
    validation_failures: int = 0
    duration_seconds: float = 0
    warnings: list[str] = field(default_factory=list)
    mart_counts: dict[str, int] = field(default_factory=dict)
    monitoring_status: str = "not_run"
    monitoring_findings: int = 0
    monitoring_created: int = 0
    monitoring_resolved: int = 0


def configure_logging() -> None:
    """Attach one structured handler to the nih logger."""

    handler = logging.StreamHandler()
    handler.setFormatter(PipelineFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    nih_logger = logging.getLogger("nih")
    nih_logger.handlers.clear()
    nih_logger.addHandler(handler)
    nih_logger.setLevel(logging.INFO)
    nih_logger.propagate = False


class PipelineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        fields = getattr(record, "pipeline_fields", None)
        if not fields:
            return rendered
        suffix = " ".join(f"{key}={fields[key]}" for key in fields)
        return f"{rendered} {suffix}"


def log_event(event: str, **fields: object) -> None:
    logger.info(event, extra={"pipeline_fields": fields})


def run_pipeline(
    sources: list[str] | None = None,
    *,
    fetcher=None,
    output_root: Path | None = None,
    dbt_runner: DbtRunner | None = None,
    skip_dbt: bool = False,
    verify_marts: bool = True,
    settings: Settings | None = None,
) -> PipelineResult:
    """Run the official pipeline and record the execution."""

    started = datetime.now(timezone.utc)
    try:
        settings = settings or load_settings()
    except Exception as exc:
        log_event("configuration_failed", error=exc)
        return PipelineResult(
            run_id=None,
            status="failed",
            ok=False,
            exit_code=2,
            error_message=str(exc),
        )
    if settings.warehouse_target != "postgres":
        message = "pipeline run loads PostgreSQL. Set NIH_WAREHOUSE_TARGET=postgres."
        log_event("configuration_failed", error=message)
        return PipelineResult(None, "failed", False, 2, message)

    try:
        connection = connect(settings)
    except Exception as exc:
        message = f"PostgreSQL is not reachable: {exc}"
        log_event("database_unreachable", error=exc)
        return PipelineResult(None, "failed", False, 2, message)

    run_id = str(uuid.uuid4())
    try:
        if not _try_lock(connection):
            message = (
                "Another pipeline run is already executing. "
                "Wait for it to finish, then rerun. No official rows were changed."
            )
            log_event("pipeline_busy", run_id=run_id)
            _ensure_pipeline_table(connection)
            _insert_finished_run(
                connection,
                run_id,
                started,
                "failed",
                error_message=message,
                validation_failures=1,
            )
            _record_failure_alert(run_id, message, settings)
            return PipelineResult(run_id, "failed", False, 2, message)
        _ensure_pipeline_table(connection)
        _mark_interrupted(connection)
        _insert_running(connection, run_id, started)
        log_event("pipeline_started", run_id=run_id)
        try:
            result = _execute(
                run_id,
                started,
                sources,
                fetcher=fetcher,
                output_root=output_root,
                dbt_runner=dbt_runner,
                skip_dbt=skip_dbt,
                verify_marts=verify_marts,
                settings=settings,
            )
        except Exception as exc:
            logger.exception("pipeline failed")
            result = _failed_result(run_id, started, str(exc))
        _finish(connection, result)
        if not result.ok:
            _record_failure_alert(run_id, result.error_message, settings)
        log_event(
            "pipeline_finished",
            run_id=run_id,
            status=result.status,
            duration_seconds=result.duration_seconds,
            inserted=result.records_inserted,
            updated=result.records_updated,
            unchanged=result.records_unchanged,
            rejected=result.records_rejected,
            dbt_status=result.dbt_status,
        )
        return result
    finally:
        _unlock(connection)
        connection.close()


def pipeline_history(limit: int = 20, settings: Settings | None = None) -> str:
    rows = list_runs(limit, settings)
    return format_history(rows)


def pipeline_status(today: date | None = None, settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    today = today or datetime.now(timezone.utc).date()
    with connect(settings) as connection:
        _ensure_pipeline_table(connection)
        connection.commit()
        runs = _fetch_runs(connection, 1)
        documents = _document_as_ofs(connection)
        counts = _fact_counts(connection)
    lines = ["Nintendo Intelligence Hub pipeline status"]
    if not runs:
        lines.append("latest run: none")
    else:
        latest = runs[0]
        lines.append(f"latest run: {latest['pipeline_run_id']}")
        lines.append(f"status: {latest['status']}")
        lines.append(f"started: {latest['started_at']}")
        lines.append(f"duration_seconds: {latest['duration_seconds']}")
        lines.append(f"dbt_status: {latest['dbt_status']}")
        lines.append(
            "records: "
            f"extracted={latest['records_extracted']} inserted={latest['records_inserted']} "
            f"updated={latest['records_updated']} unchanged={latest['records_unchanged']} "
            f"rejected={latest['records_rejected']}"
        )
    lines.extend(format_freshness(documents, today))
    lines.append(
        "warehouse: "
        f"official unit rows {counts['official_unit_rows']}, "
        f"official financial rows {counts['official_financial_rows']}, "
        f"simulated rows {counts['simulated_rows']}"
    )
    lines.append(
        "quarterly marts: empty until a source file contains q1, q1_q2, or q1_q3 columns. "
        "An empty quarterly mart is not a freshness failure."
    )
    try:
        from monitoring.engine import monitoring_status

        monitor = monitoring_status(settings)
        active = monitor["active_by_severity"]
        lines.append(
            "monitoring: "
            f"health={monitor['health']} critical={active.get('critical', 0)} "
            f"warning={active.get('warning', 0)} info={active.get('info', 0)}"
        )
        latest_eval = monitor["latest_evaluation"]
        if latest_eval:
            lines.append(
                f"latest monitoring evaluation: {latest_eval['status']} at {latest_eval['started_at']}"
            )
    except Exception as exc:
        lines.append(f"monitoring: unavailable ({exc})")
    issues = outstanding_issues(runs[0] if runs else None, documents, today)
    if issues:
        lines.append("outstanding issues:")
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("outstanding issues: none")
    return "\n".join(lines)


def list_runs(limit: int = 20, settings: Settings | None = None) -> list[dict]:
    settings = settings or load_settings()
    with connect(settings) as connection:
        _ensure_pipeline_table(connection)
        connection.commit()
        return _fetch_runs(connection, limit)


def format_history(rows: list[dict]) -> str:
    if not rows:
        return "No pipeline runs are recorded."
    header = (
        "run_id status started duration_s extracted inserted updated "
        "unchanged rejected dbt validation_failures"
    )
    lines = [header]
    for row in rows:
        lines.append(
            " ".join(
                [
                    str(row["pipeline_run_id"]),
                    str(row["status"]),
                    str(row["started_at"]),
                    str(row["duration_seconds"]),
                    str(row["records_extracted"]),
                    str(row["records_inserted"]),
                    str(row["records_updated"]),
                    str(row["records_unchanged"]),
                    str(row["records_rejected"]),
                    str(row["dbt_status"]),
                    str(row["validation_failures"]),
                ]
            )
        )
        error = (row.get("error_message") or "").strip()
        if error:
            lines.append(f"  error: {error.splitlines()[0]}")
    return "\n".join(lines)


def mandatory_problems(outcomes: list[SourceOutcome]) -> list[str]:
    problems = []
    for outcome in outcomes:
        if outcome.source_id not in OFFICIAL_SOURCES:
            continue
        if outcome.status != "loaded":
            problems.append(f"{outcome.source_id} is {outcome.status}. {outcome.message}")
        elif outcome.accepted <= 0:
            problems.append(f"{outcome.source_id} accepted no official rows. {outcome.message}")
        if outcome.warehouse_error:
            problems.append(f"{outcome.source_id} warehouse load failed: {outcome.warehouse_error}")
    return problems


def optional_warnings(outcomes: list[SourceOutcome]) -> list[str]:
    warnings = []
    for outcome in outcomes:
        if outcome.source_id in OPTIONAL_SOURCES and outcome.status != "loaded":
            warnings.append(f"{outcome.source_id} is {outcome.status}. {outcome.message}")
    return warnings


def cadence_for(source_document_id: str) -> str:
    if source_document_id.startswith(("nintendo_sales_transition", "nintendo_income_transition")):
        return "annual_historical"
    if source_document_id.startswith(("nintendo_dedicated_units", "nintendo_top_titles")):
        return "quarterly_page"
    return "unscheduled"


def expected_as_of(today: date, cadence: str) -> date | None:
    """Return the oldest as-of date that is still inside the publication window."""

    if cadence == "annual_historical":
        this_close = date(today.year, 3, 31)
        if (today - this_close).days >= ANNUAL_PUBLICATION_LAG_DAYS:
            return this_close
        return date(today.year - 1, 3, 31)
    if cadence == "quarterly_page":
        candidates = []
        for year in (today.year - 1, today.year):
            candidates.extend(
                [
                    date(year, 3, 31),
                    date(year, 6, 30),
                    date(year, 9, 30),
                    date(year, 12, 31),
                ]
            )
        eligible = [day for day in candidates if timedelta(days=0) <= today - day and (today - day).days >= QUARTERLY_PUBLICATION_LAG_DAYS]
        return max(eligible) if eligible else None
    return None


def freshness_findings(documents: list[tuple[str, date]], today: date) -> list[str]:
    """Return overdue findings. A current annual file is not called stale."""

    findings = []
    for cadence, label in (
        ("annual_historical", "annual historical workbook"),
        ("quarterly_page", "quarterly IR page"),
    ):
        dated = [
            (document_id, as_of)
            for document_id, as_of in documents
            if cadence_for(document_id) == cadence and as_of <= today
        ]
        expected = expected_as_of(today, cadence)
        if not dated:
            findings.append(f"No {label} as-of date is loaded.")
            continue
        newest_id, newest = max(dated, key=lambda item: item[1])
        if expected is not None and newest < expected:
            findings.append(
                f"{label} is overdue: newest as-of {newest.isoformat()} on {newest_id} "
                f"is before the publication window {expected.isoformat()}."
            )
    return findings


def format_freshness(documents: list[tuple[str, date]], today: date) -> list[str]:
    lines = []
    usable = [(document_id, as_of) for document_id, as_of in documents if as_of <= today]
    if usable:
        newest = max(as_of for _, as_of in usable)
        lines.append(f"latest official as-of: {newest.isoformat()}")
    else:
        lines.append("latest official as-of: none")
    for cadence, label in (
        ("annual_historical", "annual publication schedule"),
        ("quarterly_page", "quarterly publication schedule"),
    ):
        dated = [as_of for document_id, as_of in usable if cadence_for(document_id) == cadence]
        expected = expected_as_of(today, cadence)
        if not dated or expected is None:
            lines.append(f"{label}: no loaded as-of date")
            continue
        newest = max(dated)
        state = "current" if newest >= expected else "overdue"
        lines.append(
            f"{label}: {state} (newest as-of {newest.isoformat()}, "
            f"expected on or after {expected.isoformat()})"
        )
    return lines


def outstanding_issues(
    latest: dict | None,
    documents: list[tuple[str, date]],
    today: date,
) -> list[str]:
    issues = []
    if latest and latest["status"] != "succeeded":
        message = (latest.get("error_message") or "").strip() or latest["status"]
        issues.append(f"latest run {latest['status']}: {message.splitlines()[0]}")
    elif latest:
        detail = latest.get("detail") or {}
        for warning in detail.get("warnings") or []:
            issues.append(f"optional source: {warning}")
    issues.extend(freshness_findings(documents, today))
    return issues


def mart_problems(counts: dict[str, int]) -> list[str]:
    """Return mart problems. An empty quarterly mart is expected and is not one."""

    problems = []
    for name in REQUIRED_MARTS:
        if name not in counts:
            problems.append(f"{name} is not queryable")
    if "weekly_sell_through" not in counts:
        problems.append("weekly_sell_through is not queryable")
    official_units = counts.get("official_unit_rows", 0)
    official_financial = counts.get("official_financial_rows", 0)
    simulated = counts.get("simulated_rows", 0)
    if official_units > 0:
        for name in UNIT_MARTS:
            if counts.get(name, 0) <= 0:
                problems.append(f"{name} has no rows while official unit facts are loaded")
    if official_financial > 0 and counts.get("mart_financial_performance", 0) <= 0:
        problems.append("mart_financial_performance has no rows while official financial facts are loaded")
    if simulated > 0 and counts.get("weekly_sell_through", 0) != simulated:
        problems.append(
            "mart_simulated.weekly_sell_through does not match the simulated fact count"
        )
    if counts.get("reported_non_official", 0) > 0:
        problems.append("an official mart contains a non-official source class")
    if counts.get("simulated_non_simulated", 0) > 0:
        problems.append("the simulated mart contains a non-simulated source class")
    return problems


def default_dbt_runner() -> DbtResult:
    executable = _dbt_executable()
    if executable is None:
        return DbtResult("failed", "dbt was not found on PATH or in the active virtualenv.")
    command = [
        executable,
        "build",
        "--project-dir",
        "transformations/dbt",
        "--profiles-dir",
        "transformations/dbt",
    ]
    log_event("dbt_started", command=" ".join(command))
    try:
        completed = subprocess.run(
            command,
            cwd=project_root(),
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return DbtResult("failed", "dbt build exceeded 600 seconds.")
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    tail = output[-2000:]
    if completed.returncode != 0:
        log_event("dbt_failed", returncode=completed.returncode)
        return DbtResult("failed", tail or f"dbt build exited {completed.returncode}")
    log_event("dbt_succeeded")
    return DbtResult("success", "dbt build succeeded")


def _execute(
    run_id: str,
    started: datetime,
    sources: list[str] | None,
    *,
    fetcher,
    output_root: Path | None,
    dbt_runner: DbtRunner | None,
    skip_dbt: bool,
    verify_marts: bool,
    settings: Settings,
) -> PipelineResult:
    outcomes = run_ingestion(
        sources,
        fetcher=fetcher,
        output_root=output_root,
        load_warehouse=True,
    )
    for outcome in outcomes:
        log_event(
            "source_finished",
            source_id=outcome.source_id,
            status=outcome.status,
            accepted=outcome.accepted,
            rejected=outcome.rejected,
            inserted=outcome.records_inserted,
            updated=outcome.records_updated,
            unchanged=outcome.records_unchanged,
            removed=outcome.records_removed,
        )
    problems = mandatory_problems(outcomes)
    warnings = optional_warnings(outcomes)
    for warning in warnings:
        log_event("optional_source_warning", message=warning)
    documents_processed = sum(
        outcome.parsed_documents for outcome in outcomes if outcome.source_id in OFFICIAL_SOURCES
    )
    extracted = sum(outcome.accepted + outcome.rejected for outcome in outcomes if outcome.source_id in OFFICIAL_SOURCES)
    inserted = sum(outcome.records_inserted for outcome in outcomes)
    updated = sum(outcome.records_updated for outcome in outcomes)
    unchanged = sum(outcome.records_unchanged for outcome in outcomes)
    rejected = sum(outcome.rejected for outcome in outcomes if outcome.source_id in OFFICIAL_SOURCES)

    audit_error = ""
    counts: dict[str, int] = {}
    try:
        from warehouse.audit import audit_database

        audited = audit_database(settings)
        counts.update(audited)
        log_event(
            "warehouse_audit_ok",
            official_unit_rows=audited["official_unit_rows"],
            official_financial_rows=audited["official_financial_rows"],
            simulated_rows=audited["simulated_rows"],
        )
    except Exception as exc:
        audit_error = str(exc)
        problems.append(audit_error)
        log_event("warehouse_audit_failed", error=exc)

    if skip_dbt:
        dbt_result = DbtResult("skipped", "dbt build was not requested")
    elif audit_error:
        dbt_result = DbtResult("not_run", "dbt build was not started because the warehouse audit failed")
    else:
        dbt_result = (dbt_runner or default_dbt_runner)()
        if dbt_result.status != "success":
            problems.append(f"dbt build {dbt_result.status}: {dbt_result.message}")

    mart_counts: dict[str, int] = {}
    if verify_marts and not audit_error and dbt_result.status == "success":
        try:
            mart_counts = _mart_counts(settings)
            counts.update(mart_counts)
            problems.extend(mart_problems(counts))
        except Exception as exc:
            problems.append(f"mart verification failed: {exc}")
            log_event("mart_verification_failed", error=exc)
    elif verify_marts and dbt_result.status != "success":
        log_event("mart_verification_skipped", dbt_status=dbt_result.status)

    monitoring_status = "not_run"
    monitoring_findings = monitoring_created = monitoring_resolved = 0
    if not problems and verify_marts and dbt_result.status == "success":
        # Post-dbt monitoring. Imported lazily: monitoring.engine reads
        # nih.pipeline freshness helpers, so a top-level import would cycle.
        try:
            from monitoring.engine import run_evaluation

            evaluation = run_evaluation(pipeline_run_id=run_id, settings=settings)
            monitoring_status = evaluation.status
            monitoring_findings = evaluation.findings
            monitoring_created = evaluation.created
            monitoring_resolved = evaluation.resolved
            log_event(
                "monitoring_finished",
                status=evaluation.status,
                findings=evaluation.findings,
                created=evaluation.created,
                resolved=evaluation.resolved,
            )
            if not evaluation.ok:
                problems.append(f"monitoring evaluation failed: {evaluation.error_message}")
        except Exception as exc:
            monitoring_status = "failed"
            problems.append(f"monitoring evaluation failed: {exc}")
            logger.exception("monitoring evaluation failed")

    error_message = "\n".join(problems)[:4000]
    status = "failed" if problems else "succeeded"
    return PipelineResult(
        run_id=run_id,
        status=status,
        ok=not problems,
        exit_code=0 if not problems else 1,
        error_message=error_message,
        documents_processed=documents_processed,
        records_extracted=extracted,
        records_inserted=inserted,
        records_updated=updated,
        records_unchanged=unchanged,
        records_rejected=rejected,
        dbt_status=dbt_result.status,
        validation_failures=len(problems),
        duration_seconds=_duration(started),
        warnings=warnings,
        mart_counts=mart_counts,
        monitoring_status=monitoring_status,
        monitoring_findings=monitoring_findings,
        monitoring_created=monitoring_created,
        monitoring_resolved=monitoring_resolved,
    )


def _record_failure_alert(run_id: str | None, message: str, settings: Settings) -> None:
    """Record a critical alert for a failed run. Failures here are logged."""
    try:
        from monitoring.engine import record_pipeline_failure

        record_pipeline_failure(
            pipeline_run_id=run_id,
            message=message or "pipeline run failed",
            settings=settings,
        )
    except Exception:
        logger.exception("could not record the pipeline failure alert")


def _failed_result(run_id: str, started: datetime, message: str) -> PipelineResult:
    return PipelineResult(
        run_id=run_id,
        status="failed",
        ok=False,
        exit_code=1,
        error_message=message[:4000],
        dbt_status="not_run",
        validation_failures=1,
        duration_seconds=_duration(started),
    )


def _duration(started: datetime) -> float:
    return round((datetime.now(timezone.utc) - started).total_seconds(), 3)


@contextmanager
def pipeline_lock(settings: Settings | None = None):
    """Hold the session advisory lock until the guarded work finishes."""

    connection = connect(settings)
    locked = False
    try:
        locked = _try_lock(connection)
        if not locked:
            raise PipelineBusy(
                "Another pipeline run is already executing. "
                "Wait for it to finish, then rerun. No official rows were changed."
            )
        yield connection
    finally:
        if locked:
            _unlock(connection)
        connection.close()


def _try_lock(connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,))
        return bool(cursor.fetchone()[0])


def _unlock(connection) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
            cursor.fetchone()
        connection.commit()
    except Exception:
        logger.exception("pipeline lock release failed")


def _ensure_pipeline_table(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('meta.pipeline_runs')")
        if cursor.fetchone()[0] is not None:
            return
        script = project_root() / "warehouse" / "ddl" / "050_pipeline_runs.sql"
        for statement in split_sql(script.read_text(encoding="utf-8")):
            cursor.execute(statement)
    connection.commit()


def _mark_interrupted(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update meta.pipeline_runs
            set status = 'failed',
                finished_at = coalesce(finished_at, now()),
                error_message = case
                    when error_message = '' then 'The previous run did not finish and was marked interrupted.'
                    else error_message
                end,
                validation_failures = greatest(validation_failures, 1)
            where status = 'running'
            """
        )
    connection.commit()


def _insert_running(connection, run_id: str, started: datetime) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into meta.pipeline_runs (
                pipeline_run_id, started_at, status
            ) values (%s, %s, 'running')
            """,
            (run_id, started),
        )
    connection.commit()


def _insert_finished_run(
    connection,
    run_id: str,
    started: datetime,
    status: str,
    *,
    error_message: str,
    validation_failures: int,
) -> None:
    finished = datetime.now(timezone.utc)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into meta.pipeline_runs (
                pipeline_run_id, started_at, finished_at, status, error_message,
                validation_failures, duration_seconds, dbt_status
            ) values (%s, %s, %s, %s, %s, %s, %s, 'not_run')
            """,
            (
                run_id,
                started,
                finished,
                status,
                error_message[:4000],
                validation_failures,
                round((finished - started).total_seconds(), 3),
            ),
        )
    connection.commit()


def _finish(connection, result: PipelineResult) -> None:
    from psycopg.types.json import Json

    finished = datetime.now(timezone.utc)
    detail = {
        "warnings": result.warnings,
        "marts": result.mart_counts,
        "monitoring": {
            "status": result.monitoring_status,
            "findings": result.monitoring_findings,
            "created": result.monitoring_created,
            "resolved": result.monitoring_resolved,
        },
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update meta.pipeline_runs
            set finished_at = %s,
                status = %s,
                documents_processed = %s,
                records_extracted = %s,
                records_inserted = %s,
                records_updated = %s,
                records_unchanged = %s,
                records_rejected = %s,
                dbt_status = %s,
                validation_failures = %s,
                error_message = %s,
                duration_seconds = %s,
                detail = %s
            where pipeline_run_id = %s
            """,
            (
                finished,
                result.status,
                result.documents_processed,
                result.records_extracted,
                result.records_inserted,
                result.records_updated,
                result.records_unchanged,
                result.records_rejected,
                result.dbt_status,
                result.validation_failures,
                result.error_message,
                result.duration_seconds,
                Json(detail),
                result.run_id,
            ),
        )
    connection.commit()


def _fetch_runs(connection, limit: int) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
                pipeline_run_id, started_at, finished_at, status, documents_processed,
                records_extracted, records_inserted, records_updated, records_unchanged,
                records_rejected, dbt_status, validation_failures, error_message,
                duration_seconds, detail
            from meta.pipeline_runs
            order by started_at desc
            limit %s
            """,
            (limit,),
        )
        columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _document_as_ofs(connection) -> list[tuple[str, date]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select source_document_id, max(as_of_date)
            from (
                select source_document_id, as_of_date
                from raw_official.unit_sales_disclosure
                union all
                select source_document_id, as_of_date
                from raw_official.financial_line
            ) as documents
            group by source_document_id
            """
        )
        return [(document_id, as_of) for document_id, as_of in cursor.fetchall()]


def _fact_counts(connection) -> dict[str, int]:
    with connection.cursor() as cursor:
        cursor.execute("select count(*) from raw_official.unit_sales_disclosure")
        units = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from raw_official.financial_line")
        financial = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from raw_simulated.weekly_sell_through")
        simulated = int(cursor.fetchone()[0])
    return {
        "official_unit_rows": units,
        "official_financial_rows": financial,
        "simulated_rows": simulated,
    }


def _mart_counts(settings: Settings) -> dict[str, int]:
    counts: dict[str, int] = {}
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            for name in REQUIRED_MARTS:
                cursor.execute(f"select count(*) from mart_reported.{name}")
                counts[name] = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from mart_simulated.weekly_sell_through")
            counts["weekly_sell_through"] = int(cursor.fetchone()[0])
            cursor.execute(
                """
                select
                    (select count(*) from mart_reported.mart_annual_platform_performance where source_class <> 'official_ir')
                    + (select count(*) from mart_reported.mart_financial_performance where source_class <> 'official_ir')
                    + (select count(*) from mart_reported.mart_lifetime_platform_sales where source_class <> 'official_ir')
                """
            )
            counts["reported_non_official"] = int(cursor.fetchone()[0])
            cursor.execute(
                """
                select count(*)
                from mart_simulated.weekly_sell_through
                where source_class <> 'simulated_operational'
                """
            )
            counts["simulated_non_simulated"] = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from raw_official.unit_sales_disclosure")
            counts["official_unit_rows"] = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from raw_official.financial_line")
            counts["official_financial_rows"] = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from raw_simulated.weekly_sell_through")
            counts["simulated_rows"] = int(cursor.fetchone()[0])
    return counts


def _dbt_executable() -> str | None:
    candidate = Path(sys.prefix) / "bin" / "dbt"
    if candidate.exists():
        return str(candidate)
    return shutil.which("dbt")
