"""Command line for the local warehouse foundation."""

from __future__ import annotations

import argparse
import logging
from datetime import date
from decimal import Decimal

from ingestion.registry import load_metric_catalog, load_source_catalog
from nih import __version__
from nih.config import describe_target, load_settings
from nih.errors import ConfigurationError, NihError
from nih.fiscal import fiscal_quarter, fiscal_year_ending
from nih.periods import (
    DisclosureMeasure,
    PeriodSpan,
    ProductGrain,
    derive_reported_incremental,
)
from nih.provenance import SourceClass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nih")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="Print the foundation version")
    check = sub.add_parser("check", help="Validate catalogs and the grain self-check")
    check.add_argument(
        "--require-db",
        action="store_true",
        help="Fail when local PostgreSQL cannot be audited",
    )
    sub.add_parser("init-db", help="Apply DDL, reference data, and the synthetic sample")
    ingest = sub.add_parser("ingest", help="Download and parse public sources")
    ingest.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Source id to ingest. Repeat to select more than one. Default: all sources.",
    )
    ingest.add_argument(
        "--skip-warehouse",
        action="store_true",
        help="Write raw and cleaned files without loading PostgreSQL",
    )
    pipeline = sub.add_parser("pipeline", help="Run or inspect the orchestrated ETL pipeline")
    pipeline_commands = pipeline.add_subparsers(dest="pipeline_command", required=True)
    run = pipeline_commands.add_parser("run", help="Ingest, validate, load, and build marts")
    run.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Source id to include. Repeat to select more than one. Default: all sources.",
    )
    run.add_argument(
        "--skip-dbt",
        action="store_true",
        help="Load and audit without running dbt build",
    )
    history = pipeline_commands.add_parser("history", help="Show recent pipeline executions")
    history.add_argument("--limit", type=int, default=20)
    pipeline_commands.add_parser("status", help="Show the latest run, freshness, and issues")
    monitor = sub.add_parser("monitor", help="Evaluate monitoring rules and inspect alerts")
    monitor_commands = monitor.add_subparsers(dest="monitor_command", required=True)
    monitor_run = monitor_commands.add_parser("run", help="Evaluate all monitoring rules and persist alerts")
    monitor_run.add_argument("--notify", action="store_true", help="Send notifications for new or reopened alerts when enabled")
    monitor_run.add_argument("--dry-run", action="store_true", help="Record what would be notified without sending anything")
    monitor_commands.add_parser("status", help="Show active alerts by severity and monitoring health")
    monitor_history = monitor_commands.add_parser("history", help="Show recent alerts and status transitions")
    monitor_history.add_argument("--limit", type=int, default=20)
    ack = monitor_commands.add_parser("ack", help="Acknowledge an alert by fingerprint or id")
    ack.add_argument("alert")
    resolve = monitor_commands.add_parser("resolve", help="Resolve an alert by fingerprint or id")
    resolve.add_argument("alert")
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "check":
        return _check(require_db=args.require_db)
    if args.command == "init-db":
        return _init_db()
    if args.command == "ingest":
        return _ingest(args.sources, load_warehouse=not args.skip_warehouse)
    if args.command == "pipeline":
        return _pipeline(args)
    if args.command == "monitor":
        return _monitor(args)
    parser.error(f"unknown command {args.command}")
    return 2


def _check(require_db: bool) -> int:
    settings = load_settings()
    sources = load_source_catalog()
    metrics = load_metric_catalog()
    _derivation_self_check()
    today = date.today()
    official = sum(1 for source in sources if source.source_class is SourceClass.OFFICIAL_IR)
    simulated = sum(
        1 for source in sources if source.source_class is SourceClass.SIMULATED_OPERATIONAL
    )
    print(f"Nintendo Intelligence Hub {__version__}")
    print(f"warehouse target: {describe_target(settings)}")
    print(f"sources: {official} official_ir, {simulated} simulated_operational")
    print(f"metrics: {len(metrics)}")
    print(
        "fiscal date: "
        f"FY3/{fiscal_year_ending(today)} Q{fiscal_quarter(today)} "
        f"({today.isoformat()})"
    )
    print("synthetic derivation self-check: ok")
    from warehouse.audit import audit_database, database_reachable

    if not database_reachable(settings):
        if require_db:
            print("database audit failed: PostgreSQL is not reachable")
            return 1
        print("database audit: skipped")
        return 0
    try:
        counts = audit_database(settings)
    except Exception as exc:
        print(f"database audit failed: {exc}")
        return 1
    print(
        "database audit: ok "
        f"(official unit rows {counts['official_unit_rows']}, "
        f"official financial rows {counts['official_financial_rows']}, "
        f"simulated rows {counts['simulated_rows']})"
    )
    return 0


def _derivation_self_check() -> None:
    """Exercise the grain rules on an obvious synthetic pair."""

    first = DisclosureMeasure(
        source_document_id="synthetic_self_check_q1",
        source_class=SourceClass.OFFICIAL_IR,
        metric_code="hw_units_sell_in",
        product_grain=ProductGrain.HARDWARE,
        platform_code="SYN_PLATFORM",
        region_code="SYN_REGION",
        fiscal_year_ending=2099,
        period_span=PeriodSpan.Q1,
        period_start=date(2098, 4, 1),
        period_end=date(2098, 6, 30),
        as_of_date=date(2098, 6, 30),
        value=Decimal("1000"),
    )
    second = DisclosureMeasure(
        source_document_id="synthetic_self_check_h1",
        source_class=SourceClass.OFFICIAL_IR,
        metric_code="hw_units_sell_in",
        product_grain=ProductGrain.HARDWARE,
        platform_code="SYN_PLATFORM",
        region_code="SYN_REGION",
        fiscal_year_ending=2099,
        period_span=PeriodSpan.Q1_Q2,
        period_start=date(2098, 4, 1),
        period_end=date(2098, 9, 30),
        as_of_date=date(2098, 9, 30),
        value=Decimal("1400"),
    )
    result = derive_reported_incremental([first, second])
    by_quarter = {row.fiscal_quarter: row for row in result.quarters}
    if by_quarter[1].incremental_value != Decimal("1000"):
        raise NihError("Q1 year-to-date should equal the first quarter")
    if by_quarter[2].incremental_value != Decimal("400"):
        raise NihError("Q2 should be the H1 cumulative minus the Q1 cumulative")
    if by_quarter[2].is_as_disclosed:
        raise NihError("a differenced quarter is marked as derived")
    if {gap.fiscal_quarter for gap in result.gaps} != {3, 4}:
        raise NihError("missing later spans should remain gaps")


def _init_db() -> int:
    from warehouse.load import initialize_database

    try:
        summary = initialize_database()
    except ConfigurationError as exc:
        print(exc)
        return 1
    print("ddl: " + ", ".join(summary["ddl_scripts"]))
    print(
        "loaded reference rows: "
        f"{summary['platforms']} platforms, {summary['regions']} regions, "
        f"{summary['metrics']} metrics, {summary['dates']} dates"
    )
    print(f"simulated weekly rows: {summary['simulated_rows']}")
    print(f"official unit rows: {summary['official_unit_rows']}")
    print(f"official financial rows: {summary['official_financial_rows']}")
    return 0


def _ingest(sources: list[str] | None, *, load_warehouse: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from ingestion.pipeline import OFFICIAL_SOURCES, genuine_official_count, run_ingestion
    from nih.errors import NihError
    from nih.pipeline import PipelineBusy, pipeline_lock

    try:
        if load_warehouse:
            with pipeline_lock():
                outcomes = run_ingestion(sources, load_warehouse=True)
        else:
            outcomes = run_ingestion(sources, load_warehouse=False)
    except PipelineBusy as exc:
        print(exc)
        return 2
    except NihError as exc:
        print(exc)
        return 1
    for outcome in outcomes:
        print(
            f"{outcome.source_id}: {outcome.status} "
            f"accepted={outcome.accepted} rejected={outcome.rejected} "
            f"missing={outcome.missing} warehouse_rows={outcome.warehouse_rows}"
        )
        print(f"  {outcome.message}")
    official = [outcome for outcome in outcomes if outcome.source_id in OFFICIAL_SOURCES]
    print(f"genuine official records accepted: {genuine_official_count(outcomes)}")
    if any(outcome.status != "loaded" for outcome in official):
        return 1
    if any(outcome.warehouse_error for outcome in outcomes):
        return 1
    return 0


def _pipeline(args) -> int:
    from nih.pipeline import configure_logging, pipeline_history, pipeline_status, run_pipeline

    configure_logging()
    if args.pipeline_command == "history":
        try:
            print(pipeline_history(args.limit))
        except Exception as exc:
            print(f"pipeline history failed: {exc}")
            return 2
        return 0
    if args.pipeline_command == "status":
        try:
            print(pipeline_status())
        except Exception as exc:
            print(f"pipeline status failed: {exc}")
            return 2
        return 0
    result = run_pipeline(args.sources, skip_dbt=args.skip_dbt)
    print(f"pipeline_run_id: {result.run_id}")
    print(f"status: {result.status}")
    print(f"duration_seconds: {result.duration_seconds}")
    print(f"documents_processed: {result.documents_processed}")
    print(
        "records: "
        f"extracted={result.records_extracted} inserted={result.records_inserted} "
        f"updated={result.records_updated} unchanged={result.records_unchanged} "
        f"rejected={result.records_rejected}"
    )
    print(f"dbt_status: {result.dbt_status}")
    print(f"validation_failures: {result.validation_failures}")
    print(
        "monitoring: "
        f"status={result.monitoring_status} findings={result.monitoring_findings} "
        f"created={result.monitoring_created} resolved={result.monitoring_resolved}"
    )
    for warning in result.warnings:
        print(f"warning: {warning}")
    if result.error_message:
        print(result.error_message)
    return result.exit_code


def _monitor(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from monitoring import engine
    from monitoring.alerts import AlertStore, ensure_monitoring_tables
    from nih.db import connect

    try:
        if args.monitor_command == "run":
            result = engine.run_evaluation(notify=args.notify, dry_run=args.dry_run)
            print(f"evaluation_id: {result.evaluation_id}")
            print(f"status: {result.status}")
            print(
                "alerts: "
                f"findings={result.findings} created={result.created} "
                f"reopened={result.reopened} updated={result.updated} resolved={result.resolved}"
            )
            active = result.active_by_severity
            print(
                "active: "
                f"critical={active.get('critical', 0)} warning={active.get('warning', 0)} "
                f"info={active.get('info', 0)}"
            )
            if result.notifications is not None:
                notes = result.notifications
                print(
                    "notifications: "
                    f"attempted={notes.attempted} sent={notes.sent} "
                    f"dry_run={notes.dry_run} skipped={notes.skipped}"
                )
            if result.error_message:
                print(result.error_message)
            return result.exit_code
        if args.monitor_command == "status":
            status = engine.monitoring_status()
            latest = status["latest_evaluation"]
            print("Nintendo Intelligence Hub monitoring status")
            print(f"health: {status['health']}")
            active = status["active_by_severity"]
            print(
                "active alerts: "
                f"critical={active.get('critical', 0)} warning={active.get('warning', 0)} "
                f"info={active.get('info', 0)}"
            )
            print(f"acknowledged: {status['acknowledged']}  resolved: {status['resolved']}")
            if latest is None:
                print("latest evaluation: none")
            else:
                print(
                    f"latest evaluation: {latest['status']} at {latest['started_at']} "
                    f"(findings {latest['findings']}, created {latest['alerts_created']}, "
                    f"resolved {latest['alerts_resolved']})"
                )
                if latest["error_message"]:
                    print(f"evaluation error: {latest['error_message']}")
            return 0
        if args.monitor_command == "history":
            alerts = engine.list_alerts(args.limit)
            events = engine.alert_events(args.limit)
            if not alerts and not events:
                print("No monitoring alerts are recorded.")
                return 0
            print("Recent alerts")
            for alert in alerts:
                print(
                    f"{alert['alert_id']} {alert['severity']} {alert['status']} {alert['alert_type']} "
                    f"{alert['platform'] or '-'} {alert['reporting_period'] or '-'} "
                    f"last={alert['last_detected_at']}"
                )
                print(f"  {alert['alert_fingerprint']}")
                print(f"  {alert['explanation']}")
            print("Recent transitions")
            for event in events:
                print(
                    f"{event['created_at']} {event['event_type']} {event['alert_type']} "
                    f"({event['severity']}) by {event['actor']}"
                )
            return 0
        # ack / resolve
        with connect() as connection:
            ensure_monitoring_tables(connection)
            connection.commit()
            store = AlertStore(connection)
            changed = (
                store.acknowledge(args.alert, actor="cli")
                if args.monitor_command == "ack"
                else store.resolve(args.alert, actor="cli")
            )
        if changed is None:
            print(f"No alert matches {args.alert}")
            return 1
        print(
            f"alert {changed['alert_id']} ({changed['fingerprint']}): "
            f"{changed['from']} -> {changed['to']}"
        )
        return 0
    except Exception as exc:
        print(f"monitor {args.monitor_command} failed: {exc}")
        return 2
