"""Phase 6 monitoring tests.

Business frames use invented FY2090s values and SYN platform codes. They
test detection arithmetic only. PostgreSQL lifecycle tests use an
isolated alert type and delete their rows afterward.
"""

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from monitoring import anomalies
from monitoring.alerts import AlertStore, Finding, ensure_monitoring_tables
from monitoring.notifications import NotificationConfig, select_notifiable, send_notifications
from monitoring.rules import Thresholds
from warehouse.audit import database_reachable

THRESHOLDS = Thresholds()


def _annual(rows):
    base = {
        "region_code": "GLOBAL",
        "period_span": "fiscal_year",
        "observation_type": "annual_flow",
        "include_in_cross_platform_total": True,
        "platform_name": "Example",
        "reconciliation_status": "exact",
        "disclosed_global_units": None,
        "regional_parts_sum": None,
    }
    return pd.DataFrame([{**base, **row} for row in rows])


def test_yoy_flags_a_large_annual_change_with_an_explanation():
    frame = _annual([
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2098, "value_units": 100.0},
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": 200.0},
    ])
    findings = anomalies.detect_platform_anomalies(frame, THRESHOLDS)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "info"
    assert finding.category == "business"
    assert "+100.0%" in finding.explanation
    assert "not evidence of a data error" in finding.explanation
    # A short history is named as a possible launch explanation.
    assert "short reported history" in finding.explanation


def test_gap_year_and_zero_prior_produce_no_change():
    frame = _annual([
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2097, "value_units": 0.0},
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": 500.0},
    ])
    assert anomalies.detect_platform_anomalies(frame, THRESHOLDS) == []


def test_lifetime_rows_are_never_compared_as_annual_flows():
    frame = _annual([
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2098, "value_units": 100.0},
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": 900.0, "period_span": "life_to_date", "observation_type": "point_in_time_cumulative"},
    ])
    assert anomalies.detect_platform_anomalies(frame, THRESHOLDS) == []
    components = _annual([
        {"platform_code": "SYN_MODEL", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2098, "value_units": 100.0, "include_in_cross_platform_total": False},
        {"platform_code": "SYN_MODEL", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": 900.0, "include_in_cross_platform_total": False},
    ])
    assert anomalies.detect_platform_anomalies(components, THRESHOLDS) == []


def test_robust_z_needs_history_and_variation():
    assert anomalies.robust_z(100.0, [10.0, 11.0]) is not None
    assert anomalies.robust_z(100.0, []) is None
    assert anomalies.robust_z(100.0, [10.0, 10.0, 10.0]) is None
    rows = [
        {"platform_code": "SYN_A", "metric_code": "sw_units_sell_in", "fiscal_year_ending": 2090 + i, "value_units": float(100 + i)}
        for i in range(5)
    ]
    # Only five observations: no robust score is attempted for the last one.
    findings = anomalies.detect_platform_anomalies(_annual(rows), THRESHOLDS)
    assert all(f.alert_type != "robust_business_movement" for f in findings)


def test_negative_values_are_kept_and_margin_moves_are_info():
    frame = _annual([
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2098, "value_units": 100.0},
        {"platform_code": "SYN_A", "metric_code": "hw_units_sell_in", "fiscal_year_ending": 2099, "value_units": -60.0},
    ])
    findings = anomalies.detect_platform_anomalies(frame, THRESHOLDS)
    assert len(findings) == 1
    assert findings[0].observed_value == -60.0

    financial = pd.DataFrame([
        {"fiscal_year_ending": 2098, "net_sales_yen": 100.0, "operating_profit_yen": 10.0, "operating_margin_calculated": 0.10},
        {"fiscal_year_ending": 2099, "net_sales_yen": 100.0, "operating_profit_yen": 20.0, "operating_margin_calculated": 0.20},
    ])
    financial_findings = anomalies.detect_financial_anomalies(financial, THRESHOLDS)
    margin = [f for f in financial_findings if f.alert_type == "margin_business_movement"]
    assert len(margin) == 1
    assert "+10.0 percentage points" in margin[0].explanation


def test_regional_rule_ignores_known_reporting_differences():
    base = {
        "region_code": "GLOBAL",
        "metric_code": "hw_units_sell_in",
        "platform_code": "SYN_A",
        "fiscal_year_ending": 2099,
    }
    incomplete = _annual([{**base, "reconciliation_status": "incomplete_breakdown", "disclosed_global_units": 1000.0, "regional_parts_sum": 10.0}])
    assert anomalies.detect_regional_deviations(incomplete, THRESHOLDS) == []
    within_tick = _annual([{**base, "reconciliation_status": "differs", "disclosed_global_units": 1_000_000.0, "regional_parts_sum": 1_005_000.0}])
    assert anomalies.detect_regional_deviations(within_tick, THRESHOLDS) == []
    beyond = _annual([{**base, "reconciliation_status": "differs", "disclosed_global_units": 1_000_000.0, "regional_parts_sum": 900_000.0}])
    findings = anomalies.detect_regional_deviations(beyond, THRESHOLDS)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_fingerprint_is_stable_and_notifications_dedupe_and_dry_run():
    one = Finding("test_type", "business", "info", "first", platform="SYN_A", reporting_period="FY3/2099")
    two = Finding("test_type", "business", "info", "changed wording", platform="SYN_A", reporting_period="FY3/2099")
    assert one.fingerprint == two.fingerprint
    config = NotificationConfig(enabled=False, min_severity="info")
    chosen = select_notifiable([one, two], config)
    assert len(chosen) == 1
    result = send_notifications([one, two], config=config, dry_run=True)
    assert result.dry_run == 1
    assert result.sent == 0
    disabled = send_notifications([one], config=NotificationConfig(enabled=False, min_severity="info"))
    assert disabled.skipped == 1
    assert disabled.sent == 0


@pytest.mark.integration
def test_alert_lifecycle_dedupes_acknowledges_resolves_and_reopens():
    if not database_reachable():
        pytest.skip("PostgreSQL is not running")
    from nih.db import connect

    finding = Finding(
        "test_lifecycle_alert",
        "data_quality",
        "warning",
        "Isolated lifecycle fixture.",
        source_name="test",
        platform="SYN_TEST",
        reporting_period="FY3/2099",
    )
    with connect() as connection:
        ensure_monitoring_tables(connection)
        connection.commit()
        _delete_test_alerts(connection)
        store = AlertStore(connection)
        try:
            first = store.sync([finding], evaluation_id=None, complete=False)
            assert len(first.created) == 1
            second = store.sync([finding], evaluation_id=None, complete=False)
            assert len(second.created) == 0
            assert len(second.updated) == 1
            assert _test_alert_count(connection) == 1

            changed = store.acknowledge(finding.fingerprint, actor="test")
            assert changed is not None and changed["to"] == "acknowledged"
            changed = store.resolve(finding.fingerprint, actor="test")
            assert changed is not None and changed["to"] == "resolved"

            reopened = store.sync([finding], evaluation_id=None, complete=False)
            assert len(reopened.reopened) == 1
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select status, detection_count
                    from meta.monitoring_alerts
                    where alert_fingerprint = %s
                    """,
                    (finding.fingerprint,),
                )
                status, detections = cursor.fetchone()
                cursor.execute(
                    """
                    select event_type
                    from meta.monitoring_alert_events
                    where alert_id = (
                        select alert_id from meta.monitoring_alerts where alert_fingerprint = %s
                    )
                    order by event_id
                    """,
                    (finding.fingerprint,),
                )
                events = [row[0] for row in cursor.fetchall()]
            assert status == "active"
            assert detections >= 3
            assert events == ["created", "seen", "acknowledged", "resolved", "reopened"]
        finally:
            _delete_test_alerts(connection)


@pytest.mark.integration
def test_live_evaluation_is_idempotent_and_preserves_official_counts():
    if not database_reachable():
        pytest.skip("PostgreSQL is not running")
    from monitoring.engine import run_evaluation
    from dashboards import queries

    before_units = len(queries.annual_performance())
    before_counts = queries.warehouse_counts()
    first = run_evaluation()
    assert first.ok, first.error_message
    second = run_evaluation()
    assert second.ok, second.error_message
    assert second.created == 0
    assert second.reopened == 0
    assert queries.warehouse_counts() == before_counts
    assert len(queries.annual_performance()) == before_units


def _test_alert_count(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "select count(*) from meta.monitoring_alerts where alert_type = 'test_lifecycle_alert'"
        )
        return int(cursor.fetchone()[0])


def _delete_test_alerts(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "delete from meta.monitoring_alerts where alert_type = 'test_lifecycle_alert'"
        )
    connection.commit()
