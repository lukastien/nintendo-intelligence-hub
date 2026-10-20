create table if not exists meta.pipeline_runs (
    pipeline_run_id uuid primary key,
    started_at timestamptz not null,
    finished_at timestamptz,
    status text not null,
    documents_processed integer not null default 0,
    records_extracted integer not null default 0,
    records_inserted integer not null default 0,
    records_updated integer not null default 0,
    records_unchanged integer not null default 0,
    records_rejected integer not null default 0,
    dbt_status text not null default 'not_run',
    validation_failures integer not null default 0,
    error_message text not null default '',
    duration_seconds numeric(12, 3),
    detail jsonb not null default '{}'::jsonb,
    constraint ck_pipeline_status check (
        status in ('running', 'succeeded', 'failed')
    )
);

create index if not exists ix_pipeline_runs_started
    on meta.pipeline_runs (started_at desc);

comment on table meta.pipeline_runs is
'GRAIN: one row per orchestrated pipeline execution. This is a control table, not a sales fact. A running row left behind by a crashed process is marked failed when the next run acquires the lock.';
