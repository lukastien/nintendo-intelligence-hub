"""Alert model, stable fingerprints, and the PostgreSQL alert lifecycle."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from nih.config import project_root
from warehouse.apply import split_sql

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    alert_type: str
    category: str
    severity: str
    explanation: str
    source_name: str = ""
    metric_name: str = ""
    platform: str | None = None
    region: str | None = None
    reporting_period: str | None = None
    observed_value: float | None = None
    expected_value: float | None = None
    threshold: float | None = None
    source_document_id: str | None = None
    pipeline_run_id: str | None = None
    # Only findings from a complete evaluation of their rule may close an
    # alert. A source that was unavailable never resolves its own alert.
    auto_resolvable: bool = True

    @property
    def fingerprint(self) -> str:
        parts = [
            self.alert_type,
            self.source_name,
            self.metric_name,
            self.platform or "",
            self.region or "",
            self.reporting_period or "",
            self.source_document_id or "",
        ]
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return f"{self.alert_type}:{digest[:24]}"


@dataclass
class SyncResult:
    created: list[Finding] = field(default_factory=list)
    reopened: list[Finding] = field(default_factory=list)
    updated: list[Finding] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)


def ensure_monitoring_tables(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('meta.monitoring_alerts')")
        if cursor.fetchone()[0] is not None:
            return
        script = project_root() / "warehouse" / "ddl" / "060_monitoring.sql"
        for statement in split_sql(script.read_text(encoding="utf-8")):
            cursor.execute(statement)
    connection.commit()


class AlertStore:
    """Persist findings with fingerprint deduplication and an audit trail."""

    def __init__(self, connection) -> None:
        self.connection = connection

    def sync(
        self,
        findings: list[Finding],
        *,
        evaluation_id: str | None,
        complete: bool,
        now: datetime | None = None,
    ) -> SyncResult:
        """Insert, update, reopen, and (only when complete) resolve alerts."""
        moment = now or datetime.now(timezone.utc)
        result = SyncResult()
        seen: set[str] = set()
        with self.connection.cursor() as cursor:
            for finding in findings:
                fingerprint = finding.fingerprint
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                cursor.execute(
                    "select alert_id, status from meta.monitoring_alerts where alert_fingerprint = %s",
                    (fingerprint,),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """
                        insert into meta.monitoring_alerts (
                            alert_fingerprint, alert_type, category, severity, status,
                            source_name, metric_name, platform, region, reporting_period,
                            observed_value, expected_value, threshold, explanation,
                            source_document_id, pipeline_run_id,
                            first_detected_at, last_detected_at
                        ) values (%s, %s, %s, %s, 'active', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        returning alert_id
                        """,
                        (
                            fingerprint,
                            finding.alert_type,
                            finding.category,
                            finding.severity,
                            finding.source_name,
                            finding.metric_name,
                            finding.platform,
                            finding.region,
                            finding.reporting_period,
                            finding.observed_value,
                            finding.expected_value,
                            finding.threshold,
                            finding.explanation,
                            finding.source_document_id,
                            finding.pipeline_run_id,
                            moment,
                            moment,
                        ),
                    )
                    alert_id = cursor.fetchone()[0]
                    self._event(cursor, alert_id, evaluation_id, "created", finding.explanation)
                    result.created.append(finding)
                    continue
                alert_id, status = row
                if status == "resolved":
                    cursor.execute(
                        """
                        update meta.monitoring_alerts
                        set status = 'active', resolved_at = null, acknowledged_at = null,
                            severity = %s, explanation = %s, observed_value = %s,
                            expected_value = %s, threshold = %s,
                            last_detected_at = %s, detection_count = detection_count + 1,
                            pipeline_run_id = coalesce(%s, pipeline_run_id)
                        where alert_id = %s
                        """,
                        (
                            finding.severity,
                            finding.explanation,
                            finding.observed_value,
                            finding.expected_value,
                            finding.threshold,
                            moment,
                            finding.pipeline_run_id,
                            alert_id,
                        ),
                    )
                    self._event(cursor, alert_id, evaluation_id, "reopened", finding.explanation)
                    result.reopened.append(finding)
                else:
                    cursor.execute(
                        """
                        update meta.monitoring_alerts
                        set severity = %s, explanation = %s, observed_value = %s,
                            expected_value = %s, threshold = %s,
                            last_detected_at = %s, detection_count = detection_count + 1,
                            pipeline_run_id = coalesce(%s, pipeline_run_id)
                        where alert_id = %s
                        """,
                        (
                            finding.severity,
                            finding.explanation,
                            finding.observed_value,
                            finding.expected_value,
                            finding.threshold,
                            moment,
                            finding.pipeline_run_id,
                            alert_id,
                        ),
                    )
                    self._event(cursor, alert_id, evaluation_id, "seen", finding.explanation)
                    result.updated.append(finding)
            if complete:
                cursor.execute(
                    "select alert_id, alert_fingerprint, alert_type from meta.monitoring_alerts where status in ('active', 'acknowledged')"
                )
                for alert_id, fingerprint, alert_type in cursor.fetchall():
                    if fingerprint in seen:
                        continue
                    # Pipeline-failure alerts are resolved by their own rule
                    # (a later successful run), never by absence here.
                    if alert_type == "pipeline_failure":
                        continue
                    cursor.execute(
                        """
                        update meta.monitoring_alerts
                        set status = 'resolved', resolved_at = %s
                        where alert_id = %s
                        """,
                        (moment, alert_id),
                    )
                    self._event(cursor, alert_id, evaluation_id, "resolved", "Not detected by a complete evaluation.")
                    result.resolved.append(fingerprint)
        self.connection.commit()
        return result

    def resolve_type(self, alert_type: str, evaluation_id: str | None) -> list[str]:
        """Resolve open alerts of one type. Used when a rule turns healthy."""
        moment = datetime.now(timezone.utc)
        resolved: list[str] = []
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                select alert_id, alert_fingerprint
                from meta.monitoring_alerts
                where alert_type = %s and status in ('active', 'acknowledged')
                """,
                (alert_type,),
            )
            for alert_id, fingerprint in cursor.fetchall():
                cursor.execute(
                    "update meta.monitoring_alerts set status = 'resolved', resolved_at = %s where alert_id = %s",
                    (moment, alert_id),
                )
                self._event(cursor, alert_id, evaluation_id, "resolved", "The condition is no longer present.")
                resolved.append(fingerprint)
        self.connection.commit()
        return resolved

    def acknowledge(self, key: str, actor: str = "cli") -> dict | None:
        return self._transition(key, "acknowledged", actor)

    def resolve(self, key: str, actor: str = "cli") -> dict | None:
        return self._transition(key, "resolved", actor)

    def _transition(self, key: str, target: str, actor: str) -> dict | None:
        moment = datetime.now(timezone.utc)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                select alert_id, alert_fingerprint, status
                from meta.monitoring_alerts
                where alert_fingerprint = %s or alert_id::text = %s
                order by alert_id
                limit 1
                """,
                (key, key),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            alert_id, fingerprint, status = row
            if target == "acknowledged":
                cursor.execute(
                    """
                    update meta.monitoring_alerts
                    set status = 'acknowledged', acknowledged_at = %s
                    where alert_id = %s and status = 'active'
                    """,
                    (moment, alert_id),
                )
                event = "acknowledged"
            else:
                cursor.execute(
                    """
                    update meta.monitoring_alerts
                    set status = 'resolved', resolved_at = %s
                    where alert_id = %s and status in ('active', 'acknowledged')
                    """,
                    (moment, alert_id),
                )
                event = "resolved"
            if cursor.rowcount:
                self._event(cursor, alert_id, None, event, f"Status changed by {actor}.")
        self.connection.commit()
        return {"alert_id": alert_id, "fingerprint": fingerprint, "from": status, "to": target}

    def mark_notified(self, fingerprints: list[str], evaluation_id: str | None) -> None:
        if not fingerprints:
            return
        moment = datetime.now(timezone.utc)
        with self.connection.cursor() as cursor:
            for fingerprint in fingerprints:
                cursor.execute(
                    "select alert_id from meta.monitoring_alerts where alert_fingerprint = %s",
                    (fingerprint,),
                )
                row = cursor.fetchone()
                if row is None:
                    continue
                cursor.execute(
                    "update meta.monitoring_alerts set last_notified_at = %s where alert_id = %s",
                    (moment, row[0]),
                )
                self._event(cursor, row[0], evaluation_id, "notified", "Notification sent or dry-run recorded.")
        self.connection.commit()

    @staticmethod
    def _event(cursor, alert_id: int, evaluation_id: str | None, event_type: str, note: str) -> None:
        cursor.execute(
            """
            insert into meta.monitoring_alert_events (alert_id, evaluation_id, event_type, note)
            values (%s, %s, %s, %s)
            """,
            (alert_id, evaluation_id, event_type, note[:2000]),
        )


def new_evaluation_id() -> str:
    return str(uuid.uuid4())
