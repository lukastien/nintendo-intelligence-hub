"""Monitoring evaluation: collect findings, sync alerts, record the run.

Rules read the dbt marts and the raw official facts. They never write to
a sales fact. A rule that raises makes the evaluation failed, and a
failed evaluation resolves nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from monitoring import anomalies
from monitoring.alerts import AlertStore, Finding, ensure_monitoring_tables, new_evaluation_id
from monitoring.notifications import NotificationConfig, NotificationResult, send_notifications
from monitoring.rules import Thresholds
from nih.config import Settings, load_settings
from nih.db import connect

logger = logging.getLogger("nih.monitoring")

EXPECTED_SOURCE_FAMILIES = (
    "nintendo_dedicated_units",
    "nintendo_sales_transition",
    "nintendo_income_transition",
    "nintendo_top_titles",
)
EXPECTED_UNIT_COLUMNS = {
    "disclosure_id", "source_document_id", "source_class", "metric_code", "product_grain",
    "platform_code", "is_platform_aggregate", "is_platform_component", "parent_platform_code",
    "game_code", "region_code", "is_region_aggregate", "fiscal_year_ending", "period_span",
    "fiscal_quarter", "period_start", "period_end", "as_of_date", "value_units",
    "source_unit_scale", "source_value_as_printed", "is_forecast", "is_additive_flow",
    "sales_basis", "definition_note", "retrieved_at",
}
EXPECTED_FINANCIAL_COLUMNS = {
    "financial_line_id", "source_document_id", "source_class", "metric_code", "entity_code",
    "platform_code", "region_code", "is_region_aggregate", "fiscal_year_ending", "period_span",
    "fiscal_quarter", "period_start", "period_end", "as_of_date", "amount_as_printed",
    "printed_scale", "amount_yen", "currency_code", "is_forecast", "is_additive_flow",
    "definition_note", "retrieved_at",
}


@dataclass
class EvaluationResult:
    evaluation_id: str | None
    status: str
    ok: bool
    exit_code: int
    error_message: str = ""
    findings: int = 0
    created: int = 0
    reopened: int = 0
    updated: int = 0
    resolved: int = 0
    active_by_severity: dict[str, int] = field(default_factory=dict)
    notifications: NotificationResult | None = None


def run_evaluation(
    *,
    pipeline_run_id: str | None = None,
    thresholds: Thresholds | None = None,
    settings: Settings | None = None,
    notify: bool = False,
    dry_run: bool = False,
    notification_config: NotificationConfig | None = None,
) -> EvaluationResult:
    """Evaluate every rule once and persist the outcome."""
    settings = settings or load_settings()
    thresholds = thresholds or Thresholds.from_env()
    evaluation_id = new_evaluation_id()
    started = datetime.now(timezone.utc)
    findings: list[Finding] = []
    errors: list[str] = []
    try:
        with connect(settings) as connection:
            ensure_monitoring_tables(connection)
            _insert_evaluation(connection, evaluation_id, pipeline_run_id, started)
            collectors = [
                ("pipeline_health", lambda: _pipeline_findings(connection, pipeline_run_id)),
                ("data_quality", lambda: _data_quality_findings(connection, thresholds, evaluation_id)),
                ("business", lambda: _business_findings(connection, thresholds)),
                ("freshness", lambda: _freshness_findings(connection)),
            ]
            for name, collect in collectors:
                try:
                    found = collect()
                    # Clear any pending transaction so one rule's failure
                    # cannot abort the next rule's queries.
                    connection.rollback()
                    findings.extend(found)
                    logger.info("monitoring_rule rule=%s findings=%s", name, len(found))
                except Exception as exc:  # A rule failure fails the evaluation.
                    connection.rollback()
                    logger.exception("monitoring rule failed: %s", name)
                    errors.append(f"{name}: {exc}")
            store = AlertStore(connection)
            complete = not errors
            sync = store.sync(
                findings,
                evaluation_id=evaluation_id,
                complete=complete,
            )
            if complete and not any(f.alert_type == "pipeline_failure" for f in findings):
                # The latest run is healthy, so an earlier failure alert closes.
                # Absence alone never closes it: this branch requires a
                # complete evaluation whose pipeline rule found no failure.
                extra = store.resolve_type("pipeline_failure", evaluation_id)
                sync.resolved.extend(extra)
            notifications = None
            if notify or dry_run:
                fresh = sync.created + sync.reopened
                notifications = send_notifications(
                    fresh,
                    config=notification_config or NotificationConfig.from_env(),
                    dry_run=dry_run,
                )
                if notifications.fingerprints:
                    store.mark_notified(notifications.fingerprints, evaluation_id)
            active = _active_counts(connection)
            status = "failed" if errors else "succeeded"
            _finish_evaluation(
                connection,
                evaluation_id,
                status,
                findings=len(findings),
                created=len(sync.created),
                reopened=len(sync.reopened),
                updated=len(sync.updated),
                resolved=len(sync.resolved),
                error_message="; ".join(errors)[:4000],
                detail={
                    "thresholds": thresholds.__dict__,
                    "complete": complete,
                    "notifications": (
                        None
                        if notifications is None
                        else {
                            "attempted": notifications.attempted,
                            "sent": notifications.sent,
                            "dry_run": notifications.dry_run,
                            "skipped": notifications.skipped,
                        }
                    ),
                },
            )
            logger.info(
                "monitoring_finished evaluation=%s status=%s findings=%s created=%s reopened=%s resolved=%s",
                evaluation_id,
                status,
                len(findings),
                len(sync.created),
                len(sync.reopened),
                len(sync.resolved),
            )
            return EvaluationResult(
                evaluation_id=evaluation_id,
                status=status,
                ok=not errors,
                exit_code=0 if not errors else 1,
                error_message="; ".join(errors),
                findings=len(findings),
                created=len(sync.created),
                reopened=len(sync.reopened),
                updated=len(sync.updated),
                resolved=len(sync.resolved),
                active_by_severity=active,
                notifications=notifications,
            )
    except Exception as exc:
        logger.exception("monitoring evaluation failed before it could finish")
        return EvaluationResult(
            evaluation_id=evaluation_id,
            status="failed",
            ok=False,
            exit_code=1,
            error_message=str(exc),
        )


def record_pipeline_failure(
    *,
    pipeline_run_id: str | None,
    message: str,
    settings: Settings | None = None,
) -> None:
    """Persist a critical operational alert for a failed pipeline run.

    Called by the orchestrator after the run row is finished. The caller
    logs any exception from here; this function does not hide it.
    """
    if pipeline_run_id is None:
        return
    settings = settings or load_settings()
    finding = Finding(
        alert_type="pipeline_failure",
        category="operational",
        severity="critical",
        source_name="nih.pipeline",
        reporting_period=None,
        explanation=(
            "The latest pipeline execution failed. "
            f"Run {pipeline_run_id}: {message.splitlines()[0] if message else 'no error text recorded'}. "
            "Investigate the run in meta.pipeline_runs, fix the cause, and rerun "
            "`python -m nih pipeline run`."
        ),
        pipeline_run_id=pipeline_run_id,
        auto_resolvable=False,
    )
    with connect(settings) as connection:
        ensure_monitoring_tables(connection)
        evaluation_id = new_evaluation_id()
        started = datetime.now(timezone.utc)
        _insert_evaluation(connection, evaluation_id, pipeline_run_id, started)
        sync = AlertStore(connection).sync([finding], evaluation_id=evaluation_id, complete=False)
        _finish_evaluation(
            connection,
            evaluation_id,
            "succeeded",
            findings=1,
            created=len(sync.created),
            reopened=len(sync.reopened),
            updated=len(sync.updated),
            resolved=0,
            error_message="",
            detail={"trigger": "pipeline_failure"},
        )


def monitoring_status(settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    with connect(settings) as connection:
        ensure_monitoring_tables(connection)
        connection.commit()
        active = _active_counts(connection)
        acknowledged = _count_where(connection, "status = 'acknowledged'")
        resolved = _count_where(connection, "status = 'resolved'")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select evaluation_id, started_at, finished_at, status, findings,
                       alerts_created, alerts_reopened, alerts_resolved, error_message
                from meta.monitoring_evaluations
                order by started_at desc
                limit 1
                """
            )
            row = cursor.fetchone()
            cursor.execute("select count(*) from meta.monitoring_alerts where status in ('active', 'acknowledged')")
            open_alerts = int(cursor.fetchone()[0])
    latest = None
    if row is not None:
        latest = {
            "evaluation_id": str(row[0]),
            "started_at": row[1],
            "finished_at": row[2],
            "status": row[3],
            "findings": row[4],
            "alerts_created": row[5],
            "alerts_reopened": row[6],
            "alerts_resolved": row[7],
            "error_message": row[8],
        }
    health = "healthy"
    if active.get("critical", 0):
        health = "critical"
    elif latest is None or latest["status"] != "succeeded":
        health = "degraded"
    elif active.get("warning", 0):
        health = "warning"
    return {
        "health": health,
        "active_by_severity": active,
        "open_alerts": open_alerts,
        "acknowledged": acknowledged,
        "resolved": resolved,
        "latest_evaluation": latest,
    }


def list_alerts(limit: int = 20, settings: Settings | None = None) -> list[dict]:
    settings = settings or load_settings()
    with connect(settings) as connection:
        ensure_monitoring_tables(connection)
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select alert_id, alert_fingerprint, alert_type, category, severity, status,
                       source_name, metric_name, platform, region, reporting_period,
                       observed_value, expected_value, explanation, source_document_id,
                       first_detected_at, last_detected_at
                from meta.monitoring_alerts
                order by last_detected_at desc
                limit %s
                """,
                (int(limit),),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def alert_events(limit: int = 20, settings: Settings | None = None) -> list[dict]:
    settings = settings or load_settings()
    with connect(settings) as connection:
        ensure_monitoring_tables(connection)
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select e.event_id, e.event_type, e.actor, e.note, e.created_at,
                       a.alert_fingerprint, a.alert_type, a.severity
                from meta.monitoring_alert_events e
                join meta.monitoring_alerts a on a.alert_id = e.alert_id
                order by e.created_at desc, e.event_id desc
                limit %s
                """,
                (int(limit),),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


# --------------------------------------------------------------- collectors
def _pipeline_findings(connection, pipeline_run_id: str | None) -> list[Finding]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select pipeline_run_id, status, dbt_status, validation_failures, error_message, started_at
            from meta.pipeline_runs
            where status in ('succeeded', 'failed')
            order by started_at desc
            limit 1
            """
        )
        row = cursor.fetchone()
    if row is None:
        return [
            Finding(
                alert_type="pipeline_never_run",
                category="operational",
                severity="warning",
                source_name="nih.pipeline",
                explanation="No pipeline execution is recorded in meta.pipeline_runs. Run `python -m nih pipeline run`.",
            )
        ]
    run_id, status, dbt_status, failures, error, _started = row
    if status == "succeeded":
        return []
    return [
        Finding(
            alert_type="pipeline_failure",
            category="operational",
            severity="critical",
            source_name="nih.pipeline",
            explanation=(
                f"The latest pipeline run {run_id} is {status} (dbt {dbt_status}, "
                f"validation failures {failures}). {str(error or '').splitlines()[0] if error else ''} "
                "No official rows were replaced by that run unless the audit stage had already committed."
            ),
            pipeline_run_id=str(run_id),
            auto_resolvable=False,
        )
    ]


def _data_quality_findings(connection, thresholds: Thresholds, evaluation_id: str) -> list[Finding]:
    findings: list[Finding] = []
    with connection.cursor() as cursor:
        # Duplicate grain keys (the unique indexes should prevent these).
        cursor.execute(
            """
            select count(*) from (
                select source_document_id, metric_code, platform_code, region_code,
                       coalesce(game_code, ''), coalesce(fiscal_year_ending, 0),
                       period_span, coalesce(fiscal_quarter, 0)
                from raw_official.unit_sales_disclosure
                group by 1,2,3,4,5,6,7,8
                having count(*) > 1
            ) duplicates
            """
        )
        duplicates = int(cursor.fetchone()[0])
        if duplicates:
            findings.append(
                _critical(
                    "duplicate_official_grain",
                    "raw_official.unit_sales_disclosure",
                    f"{duplicates} duplicate unit-sales grain keys exist. The fact grain is one row per document, metric, platform, region, title, fiscal year, span, and quarter.",
                    observed=duplicates,
                )
            )
        cursor.execute(
            """
            select count(*) from (
                select source_document_id, metric_code, region_code,
                       coalesce(fiscal_year_ending, 0), period_span, coalesce(fiscal_quarter, 0)
                from raw_official.financial_line
                group by 1,2,3,4,5,6
                having count(*) > 1
            ) duplicates
            """
        )
        fin_duplicates = int(cursor.fetchone()[0])
        if fin_duplicates:
            findings.append(
                _critical(
                    "duplicate_official_grain",
                    "raw_official.financial_line",
                    f"{fin_duplicates} duplicate financial grain keys exist.",
                    observed=fin_duplicates,
                )
            )
        # Missing mandatory values and invalid periods.
        cursor.execute(
            """
            select
                count(*) filter (where metric_code is null or metric_code = '' or platform_code is null or platform_code = '' or region_code is null or region_code = ''),
                count(*) filter (where value_units is null),
                count(*) filter (where not ref.period_bounds_ok(fiscal_year_ending, period_span, fiscal_quarter, period_start, period_end))
            from raw_official.unit_sales_disclosure
            """
        )
        missing_keys, missing_values, bad_periods = cursor.fetchone()
        if missing_keys:
            findings.append(_critical("missing_mandatory_field", "raw_official.unit_sales_disclosure", f"{missing_keys} unit rows miss a metric, platform, or region code.", observed=int(missing_keys)))
        if bad_periods:
            findings.append(_critical("invalid_reporting_period", "raw_official.unit_sales_disclosure", f"{bad_periods} unit rows fail ref.period_bounds_ok for their fiscal year and span.", observed=int(bad_periods)))
        cursor.execute(
            "select count(*) from raw_official.financial_line where not ref.period_bounds_ok(fiscal_year_ending, period_span, fiscal_quarter, period_start, period_end)"
        )
        bad_fin_periods = int(cursor.fetchone()[0])
        if bad_fin_periods:
            findings.append(_critical("invalid_reporting_period", "raw_official.financial_line", f"{bad_fin_periods} financial rows fail ref.period_bounds_ok.", observed=int(bad_fin_periods)))
        # (missing_values is reported only as context: a stored null would be
        # a load defect, and the parsers never write one deliberately.)
        if missing_values:
            findings.append(
                Finding(
                    alert_type="missing_measure_value",
                    category="data_quality",
                    severity="warning",
                    source_name="raw_official.unit_sales_disclosure",
                    explanation=f"{int(missing_values)} unit rows have no normalized value. Blank source cells are normally not loaded at all, so a stored null needs review.",
                    observed_value=float(missing_values),
                )
            )
        # Synthetic/official separation.
        cursor.execute(
            """
            select
                (select count(*) from raw_official.unit_sales_disclosure where source_class <> 'official_ir'),
                (select count(*) from raw_official.financial_line where source_class <> 'official_ir' or entity_code <> 'nintendo_co_ltd_consolidated'),
                (select count(*) from raw_simulated.weekly_sell_through where source_class <> 'simulated_operational' or series_name not like 'synthetic_%')
            """
        )
        mixed = [int(value) for value in cursor.fetchone()]
        if any(mixed):
            findings.append(
                _critical(
                    "synthetic_official_mixing",
                    "warehouse",
                    f"Source-class purity failed (unit={mixed[0]}, financial={mixed[1]}, simulated={mixed[2]}). Synthetic rows must never enter official facts.",
                    observed=sum(mixed),
                )
            )
        # Required source document families.
        cursor.execute("select source_document_id from meta.source_document where source_class = 'official_ir'")
        document_ids = [str(row[0]) for row in cursor.fetchall()]
        for family in EXPECTED_SOURCE_FAMILIES:
            if not any(document_id.startswith(family) for document_id in document_ids):
                findings.append(
                    _critical(
                        "missing_source_document",
                        family,
                        f"No source document starting with {family} is registered in meta.source_document. That mandatory Nintendo IR family has not been loaded.",
                    )
                )
        # Mart availability.
        for name in (
            "mart_annual_platform_performance",
            "mart_hardware_software_trends",
            "mart_financial_performance",
            "mart_lifetime_platform_sales",
            "mart_regional_performance",
        ):
            try:
                cursor.execute(f"select count(*) from mart_reported.{name}")
                count = int(cursor.fetchone()[0])
            except Exception:
                connection.rollback()
                findings.append(_critical("mart_unavailable", f"mart_reported.{name}", f"mart_reported.{name} cannot be queried. Run dbt build."))
                continue
            if count == 0:
                findings.append(_critical("mart_unavailable", f"mart_reported.{name}", f"mart_reported.{name} has no rows while official facts are loaded."))
        # Schema drift.
        findings.extend(_schema_findings(connection))
        # Row-count change versus the previous succeeded evaluation.
        findings.extend(_row_count_findings(connection, thresholds, evaluation_id))
    return findings


def _schema_findings(connection) -> list[Finding]:
    findings: list[Finding] = []
    actual = _table_columns(connection)
    for table, expected in (
        ("unit_sales_disclosure", EXPECTED_UNIT_COLUMNS),
        ("financial_line", EXPECTED_FINANCIAL_COLUMNS),
    ):
        columns = actual.get(table)
        if columns is None:
            findings.append(_critical("source_schema_change", f"raw_official.{table}", f"raw_official.{table} is missing."))
            continue
        missing = sorted(expected - columns)
        extra = sorted(columns - expected)
        if missing:
            findings.append(
                _critical(
                    "source_schema_change",
                    f"raw_official.{table}",
                    f"Columns missing from raw_official.{table}: {', '.join(missing)}. Ingestion or DDL has drifted from the expected schema.",
                )
            )
        if extra:
            findings.append(
                Finding(
                    alert_type="source_schema_change",
                    category="data_quality",
                    severity="warning",
                    source_name=f"raw_official.{table}",
                    metric_name="unexpected_column",
                    explanation=f"Unexpected columns on raw_official.{table}: {', '.join(extra)}. Review whether the schema changed deliberately.",
                )
            )
    return findings


def _row_count_findings(connection, thresholds: Thresholds, evaluation_id: str) -> list[Finding]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select source_document_id, count(*)
            from raw_official.unit_sales_disclosure
            group by 1
            union all
            select source_document_id, count(*)
            from raw_official.financial_line
            group by 1
            order by 1
            """
        )
        current = {str(doc): int(count) for doc, count in cursor.fetchall()}
        cursor.execute(
            """
            select detail
            from meta.monitoring_evaluations
            where status = 'succeeded' and evaluation_id <> %s
            order by started_at desc
            limit 1
            """,
            (evaluation_id,),
        )
        row = cursor.fetchone()
    if row is None or not isinstance(row[0], dict):
        _stash_counts(connection, evaluation_id, current)
        return []
    previous = (row[0] or {}).get("document_row_counts") or {}
    _stash_counts(connection, evaluation_id, current)
    findings: list[Finding] = []
    for document_id, count in current.items():
        before = previous.get(document_id)
        if before is None:
            continue  # A genuinely new document is expected pipeline news.
        change = count - int(before)
        if change == 0:
            continue
        relative = abs(change) / int(before) if int(before) else 0.0
        if abs(change) >= thresholds.row_count_absolute_change and relative >= thresholds.row_count_relative_change:
            findings.append(
                Finding(
                    alert_type="source_row_count_change",
                    category="data_quality",
                    severity="warning",
                    source_name=document_id,
                    source_document_id=document_id,
                    observed_value=float(count),
                    expected_value=float(before),
                    threshold=thresholds.row_count_relative_change,
                    explanation=(
                        f"{document_id} now holds {count} rows versus {before} at the previous "
                        f"evaluation ({relative * 100:+.1f}%). A corrected disclosure can do this "
                        "legitimately; confirm the source file changed before treating it as a defect."
                    ),
                )
            )
    return findings


def _stash_counts(connection, evaluation_id: str, counts: dict[str, int]) -> None:
    from psycopg.types.json import Jsonb as Json

    with connection.cursor() as cursor:
        cursor.execute(
            """
            update meta.monitoring_evaluations
            set detail = detail || %s::jsonb
            where evaluation_id = %s
            """,
            (Json({"document_row_counts": counts}), evaluation_id),
        )
    connection.commit()


def _business_findings(connection, thresholds: Thresholds) -> list[Finding]:
    annual = _frame(
        connection,
        "select * from mart_reported.mart_annual_platform_performance",
    )
    financial = _frame(
        connection,
        "select * from mart_reported.mart_financial_performance",
    )
    findings: list[Finding] = []
    findings.extend(anomalies.detect_platform_anomalies(annual, thresholds))
    findings.extend(anomalies.detect_financial_anomalies(financial, thresholds))
    findings.extend(anomalies.detect_regional_deviations(annual, thresholds))
    return findings


def _freshness_findings(connection) -> list[Finding]:
    from nih.pipeline import freshness_findings

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select source_document_id, max(as_of_date)
            from (
                select source_document_id, as_of_date from raw_official.unit_sales_disclosure
                union all
                select source_document_id, as_of_date from raw_official.financial_line
            ) documents
            group by 1
            """
        )
        documents = [(str(doc), as_of) for doc, as_of in cursor.fetchall()]
    today = datetime.now(timezone.utc).date()
    return [
        Finding(
            alert_type="source_freshness_overdue",
            category="operational",
            severity="warning",
            source_name="nintendo_ir",
            explanation=finding + " Historical annual data is judged on its publication schedule, not on daily age.",
            auto_resolvable=True,
        )
        for finding in freshness_findings(documents, today)
    ]


def _frame(connection, sql: str) -> pd.DataFrame:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        columns = [column.name for column in cursor.description]
        rows = cursor.fetchall()
    frame = pd.DataFrame(rows, columns=columns)
    for column in frame.columns:
        if column.endswith("_units") or column.endswith("_yen") or column.endswith("_calculated"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _table_columns(connection) -> dict[str, set[str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select table_name, column_name
            from information_schema.columns
            where table_schema = 'raw_official'
            """
        )
        result: dict[str, set[str]] = {}
        for table, column in cursor.fetchall():
            result.setdefault(str(table), set()).add(str(column))
        return result


def _critical(alert_type: str, source: str, explanation: str, observed: float | None = None) -> Finding:
    return Finding(
        alert_type=alert_type,
        category="data_quality" if alert_type != "missing_source_document" else "operational",
        severity="critical",
        source_name=source,
        explanation=explanation,
        observed_value=observed,
    )


def _active_counts(connection) -> dict[str, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select severity, count(*)
            from meta.monitoring_alerts
            where status in ('active', 'acknowledged')
            group by 1
            """
        )
        counts = {"critical": 0, "warning": 0, "info": 0}
        for severity, count in cursor.fetchall():
            counts[str(severity)] = int(count)
        return counts


def _count_where(connection, where: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from meta.monitoring_alerts where {where}")
        return int(cursor.fetchone()[0])


def _insert_evaluation(connection, evaluation_id: str, pipeline_run_id: str | None, started: datetime) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into meta.monitoring_evaluations (evaluation_id, pipeline_run_id, started_at, status)
            values (%s, %s, %s, 'running')
            """,
            (evaluation_id, pipeline_run_id, started),
        )
    connection.commit()


def _finish_evaluation(
    connection,
    evaluation_id: str,
    status: str,
    *,
    findings: int,
    created: int,
    reopened: int,
    updated: int,
    resolved: int,
    error_message: str,
    detail: dict,
) -> None:
    from psycopg.types.json import Jsonb

    with connection.cursor() as cursor:
        cursor.execute(
            """
            update meta.monitoring_evaluations
            set finished_at = %s, status = %s, findings = %s,
                alerts_created = %s, alerts_reopened = %s, alerts_updated = %s,
                alerts_resolved = %s, error_message = %s,
                detail = detail || %s
            where evaluation_id = %s
            """,
            (
                datetime.now(timezone.utc),
                status,
                findings,
                created,
                reopened,
                updated,
                resolved,
                error_message,
                Jsonb(detail),
                evaluation_id,
            ),
        )
    connection.commit()
