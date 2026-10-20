-- Phase 7 forecast persistence. Forecasts live in their own schema and
-- are never written into official facts or mart_reported.

create schema if not exists forecast;

create table if not exists forecast.forecast_runs (
    run_id uuid primary key,
    started_at timestamptz not null,
    finished_at timestamptz,
    status text not null check (status in ('running', 'succeeded', 'failed')),
    model_version text not null,
    horizon_years integer not null,
    series_total integer not null default 0,
    series_forecast integer not null default 0,
    series_limited integer not null default 0,
    series_ineligible integer not null default 0,
    forecasts_written integer not null default 0,
    error_message text not null default '',
    detail jsonb not null default '{}'::jsonb
);

create table if not exists forecast.forecasts (
    forecast_id bigint generated always as identity primary key,
    run_id uuid not null references forecast.forecast_runs (run_id) on delete cascade,
    series_key text not null,
    metric_name text not null,
    platform text not null,
    platform_name text not null default '',
    region text not null default 'GLOBAL',
    train_start_year integer not null,
    train_end_year integer not null,
    train_observations integer not null,
    forecast_year integer not null,
    horizon_step integer not null,
    point_forecast double precision not null,
    point_clipped boolean not null default false,
    interval_lower double precision,
    interval_upper double precision,
    interval_level double precision not null default 0.8,
    interval_clipped boolean not null default false,
    interval_calibrated boolean not null default false,
    selected_model text not null,
    backtest_folds integer not null default 0,
    backtest_mae double precision,
    backtest_rmse double precision,
    backtest_wape double precision,
    backtest_smape double precision,
    backtest_bias double precision,
    status text not null check (status in ('selected', 'limited')),
    eligibility_note text not null default '',
    data_provenance text not null,
    model_version text not null,
    created_at timestamptz not null default now(),
    unique (run_id, series_key, forecast_year)
);

create index if not exists ix_forecasts_run on forecast.forecasts (run_id, series_key);
create index if not exists ix_forecasts_series on forecast.forecasts (series_key, forecast_year);

create table if not exists forecast.series_evaluations (
    evaluation_id bigint generated always as identity primary key,
    run_id uuid not null references forecast.forecast_runs (run_id) on delete cascade,
    series_key text not null,
    metric_name text not null,
    platform text not null,
    model_name text not null,
    train_observations integer not null,
    backtest_folds integer not null default 0,
    mae double precision,
    rmse double precision,
    wape double precision,
    smape double precision,
    bias double precision,
    selected boolean not null default false,
    fit_failures integer not null default 0,
    unique (run_id, series_key, model_name)
);

create table if not exists forecast.backtest_folds (
    fold_id bigint generated always as identity primary key,
    run_id uuid not null references forecast.forecast_runs (run_id) on delete cascade,
    series_key text not null,
    model_name text not null,
    target_year integer not null,
    train_observations integer not null,
    prediction double precision not null,
    actual double precision not null,
    error double precision not null,
    unique (run_id, series_key, model_name, target_year)
);

comment on table forecast.forecast_runs is
'GRAIN: one row per forecasting run. Forecasts are independent statistical estimates, never official Nintendo guidance.';

comment on table forecast.forecasts is
'GRAIN: one row per run, series, and forecast fiscal year. Point forecasts with residual-based 80 percent intervals. Stored outside mart_reported so predictions can never be mistaken for reported actuals.';

comment on table forecast.series_evaluations is
'GRAIN: one row per run, series, and candidate model, with expanding-window backtest metrics and the selection flag.';

comment on table forecast.backtest_folds is
'GRAIN: one row per run, series, model, and scored target year. Training uses only earlier fiscal years; gap years are never scored.';
