# Notification setup

Notifications are optional and disabled by default. Local development
needs no Slack workspace and no mail server.

## What gets notified

Only alerts created or reopened by that evaluation are candidates.
Alerts that are merely seen again are not re-notified. Candidates are
deduplicated by fingerprint and filtered by minimum severity.
Notifications are sent by `monitor run --notify`. The evaluation built
into `pipeline run` never sends notifications; it only persists alerts,
which a later `monitor run --notify` (for example from a scheduler) can
pick up if they are newly created or reopened at that time.

```bash
python -m nih monitor run --dry-run   # prints what would be sent, sends nothing
python -m nih monitor run --notify     # sends when enabled and configured
```

## Slack

Set in the environment or `.env` (never committed):

```text
NIH_NOTIFICATIONS_ENABLED=true
NIH_NOTIFICATION_MIN_SEVERITY=warning
NIH_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

## Email

```text
NIH_NOTIFICATIONS_ENABLED=true
NIH_SMTP_HOST=smtp.example.com
NIH_SMTP_PORT=587
NIH_SMTP_USER=...
NIH_SMTP_PASSWORD=...
NIH_NOTIFICATION_EMAIL_FROM=alerts@example.com
NIH_NOTIFICATION_EMAIL_TO=bi@example.com
```

STARTTLS is used. No credential is printed, logged, or stored in
PostgreSQL. When email settings are incomplete, the email channel is
simply not configured and the run reports that notifications were
skipped.

## Behaviour

| Setting | Result |
| --- | --- |
| `NIH_NOTIFICATIONS_ENABLED` unset or not `true` | Nothing is sent; the run reports `skipped` |
| `--dry-run` | Counts and lists what would be sent; opens no connection; works without credentials |
| Enabled but no destination | `skipped`, with the reason in the command output |
| Severity below the floor | Not selected |
| Same fingerprint twice in one batch | Sent once |

A sent (or dry-run) notification writes a `notified` event on the alert
and sets `last_notified_at`. Secrets stay in the process environment;
GitHub Actions would read them from repository secrets, exactly like the
pipeline database credentials.
