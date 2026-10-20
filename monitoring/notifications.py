"""Optional alert notifications. Disabled by default.

Configuration is environment-only:

- NIH_NOTIFICATIONS_ENABLED=true to allow real sends
- NIH_NOTIFICATION_MIN_SEVERITY=critical|warning|info (default warning)
- NIH_SLACK_WEBHOOK_URL for Slack
- NIH_SMTP_HOST, NIH_SMTP_PORT, NIH_SMTP_USER, NIH_SMTP_PASSWORD,
  NIH_NOTIFICATION_EMAIL_FROM, NIH_NOTIFICATION_EMAIL_TO for email

No credential is ever logged. Tests use dry runs or injected senders.
"""

from __future__ import annotations

import os
import smtplib
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage

from monitoring.alerts import SEVERITY_ORDER, Finding

Sender = Callable[..., None]


@dataclass
class NotificationConfig:
    enabled: bool = False
    min_severity: str = "warning"
    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    @classmethod
    def from_env(cls) -> "NotificationConfig":
        def text(name: str) -> str:
            return os.environ.get(name, "").strip()

        try:
            port = int(text("NIH_SMTP_PORT") or 587)
        except ValueError:
            port = 587
        severity = text("NIH_NOTIFICATION_MIN_SEVERITY").lower() or "warning"
        if severity not in SEVERITY_ORDER:
            severity = "warning"
        return cls(
            enabled=text("NIH_NOTIFICATIONS_ENABLED").lower() in {"1", "true", "yes"},
            min_severity=severity,
            slack_webhook_url=text("NIH_SLACK_WEBHOOK_URL"),
            smtp_host=text("NIH_SMTP_HOST"),
            smtp_port=port,
            smtp_user=text("NIH_SMTP_USER"),
            smtp_password=text("NIH_SMTP_PASSWORD"),
            email_from=text("NIH_NOTIFICATION_EMAIL_FROM"),
            email_to=text("NIH_NOTIFICATION_EMAIL_TO"),
        )

    @property
    def channels(self) -> list[str]:
        found = []
        if self.slack_webhook_url:
            found.append("slack")
        if self.smtp_host and self.email_from and self.email_to:
            found.append("email")
        return found


@dataclass
class NotificationResult:
    attempted: int = 0
    sent: int = 0
    dry_run: int = 0
    skipped: int = 0
    messages: list[str] = field(default_factory=list)
    fingerprints: list[str] = field(default_factory=list)


def select_notifiable(
    findings: list[Finding],
    config: NotificationConfig,
) -> list[Finding]:
    """New/reopened findings at or above the severity floor, deduplicated."""
    chosen: list[Finding] = []
    seen: set[str] = set()
    floor = SEVERITY_ORDER[config.min_severity]
    for finding in findings:
        if SEVERITY_ORDER[finding.severity] > floor:
            continue
        if finding.fingerprint in seen:
            continue
        seen.add(finding.fingerprint)
        chosen.append(finding)
    return chosen


def format_message(finding: Finding) -> tuple[str, str]:
    subject = f"[{finding.severity.upper()}] Nintendo Intelligence Hub: {finding.alert_type}"
    body = (
        f"{finding.explanation}\n\n"
        f"Source: {finding.source_name or 'n/a'}\n"
        f"Metric: {finding.metric_name or 'n/a'}"
        f" Platform: {finding.platform or 'n/a'}"
        f" Region: {finding.region or 'n/a'}"
        f" Period: {finding.reporting_period or 'n/a'}\n"
        f"Fingerprint: {finding.fingerprint}"
    )
    return subject, body


def send_notifications(
    findings: list[Finding],
    *,
    config: NotificationConfig | None = None,
    dry_run: bool = False,
    slack_sender: Sender | None = None,
    email_sender: Sender | None = None,
) -> NotificationResult:
    """Notify for the given findings. Dry-run never opens a connection."""
    config = config or NotificationConfig.from_env()
    result = NotificationResult()
    chosen = select_notifiable(findings, config)
    for finding in chosen:
        subject, body = format_message(finding)
        if dry_run:
            result.dry_run += 1
            result.fingerprints.append(finding.fingerprint)
            result.messages.append(f"dry-run: would notify {finding.severity} {finding.alert_type}")
            continue
        if not config.enabled:
            result.skipped += 1
            result.messages.append("notifications are disabled (NIH_NOTIFICATIONS_ENABLED is not true)")
            continue
        if not config.channels:
            result.skipped += 1
            result.messages.append("notifications enabled but no Slack webhook or email destination is configured")
            continue
        result.attempted += 1
        delivered = False
        if "slack" in config.channels:
            (slack_sender or _send_slack)(config, body)
            delivered = True
        if "email" in config.channels:
            (email_sender or _send_email)(config, subject, body)
            delivered = True
        if delivered:
            result.sent += 1
            result.fingerprints.append(finding.fingerprint)
    return result


def _send_slack(config: NotificationConfig, body: str) -> None:
    import requests

    response = requests.post(config.slack_webhook_url, json={"text": body}, timeout=15)
    if response.status_code >= 400:
        raise RuntimeError(f"Slack webhook returned HTTP {response.status_code}")


def _send_email(config: NotificationConfig, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.email_from
    message["To"] = config.email_to
    message.set_content(body)
    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
        server.starttls()
        if config.smtp_user:
            server.login(config.smtp_user, config.smtp_password)
        server.send_message(message)
