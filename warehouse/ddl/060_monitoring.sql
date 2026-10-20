create table if not exists meta.monitoring_alerts (
    alert_id bigint generated always as identity primary key,
    alert_fingerprint text not null,
    alert_type text not null,
    category text not null,
    severity text not null,
    status text not null default 'active',
    source_name text not null default '',
    metric_name text not null default '',
    platform text,
    region text,
    reporting_period text,
    observed_value numeric,
    expected_value numeric,
    threshold numeric,
    explanation text not null,
    source_document_id text,
    pipeline_run_id uuid,
    first_detected_at timestamptz not null default now(),
    last_detected_at timestamptz not null default now(),
    acknowledged_at timestamptz,
    resolved_at timestamptz,
    last_notified_at timestamptz,
    detection_count integer not null default 1,
    constraint ck_monitoring_severity check (severity in ('critical', 'warning', 'info')),
    constraint ck_monitoring_status check (status in ('active', 'acknowledged', 'resolved')),
    constraint ck_monitoring_category check (category in ('operational', 'data_quality', 'business'))
);

create unique index if not exists uq_monitoring_alert_fingerprint
    on meta.monitoring_alerts (alert_fingerprint);

create index if not exists ix_monitoring_alert_severity
    on meta.monitoring_alerts (severity, status);

create index if not exists ix_monitoring_alert_status
    on meta.monitoring_alerts (status, severity);

create index if not exists ix_monitoring_alert_detected
    on meta.monitoring_alerts (last_detected_at desc);

create table if not exists meta.monitoring_evaluations (
    evaluation_id uuid primary key,
    pipeline_run_id uuid,
    started_at timestamptz not null,
    finished_at timestamptz,
    status text not null,
    findings integer not null default 0,
    alerts_created integer not null default 0,
    alerts_reopened integer not null default 0,
    alerts_updated integer not null default 0,
    alerts_resolved integer not null default 0,
    error_message text not null default '',
    detail jsonb not null default '{}'::jsonb,
    constraint ck_monitoring_evaluation_status check (status in ('running', 'succeeded', 'failed'))
);

create index if not exists ix_monitoring_evaluations_started
    on meta.monitoring_evaluations (started_at desc);

create table if not exists meta.monitoring_alert_events (
    event_id bigint generated always as identity primary key,
    alert_id bigint not null references meta.monitoring_alerts (alert_id) on delete cascade,
    evaluation_id uuid,
    event_type text not null,
    actor text not null default 'monitoring',
    note text not null default '',
    created_at timestamptz not null default now(),
    constraint ck_monitoring_event_type check (
        event_type in ('created', 'seen', 'acknowledged', 'resolved', 'reopened', 'notified')
    )
);

create index if not exists ix_monitoring_alert_events_alert
    on meta.monitoring_alert_events (alert_id, created_at desc);

comment on table meta.monitoring_alerts is
'GRAIN: one row per stable alert fingerprint. Status changes are audited in meta.monitoring_alert_events. Known reporting differences (negative revisions, incomplete old regional breakdowns, family/component coexistence) are not alerts by themselves.';

comment on table meta.monitoring_evaluations is
'GRAIN: one row per monitoring evaluation. A failed evaluation never auto-resolves alerts.';

comment on table meta.monitoring_alert_events is
'GRAIN: one row per alert status transition (created, seen, acknowledged, resolved, reopened, notified), written by the alert store and the notification step.';
