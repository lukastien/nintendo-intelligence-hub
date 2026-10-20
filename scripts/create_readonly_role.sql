-- Read-only dashboard role for the public demo deployment.
--
-- Run as the warehouse owner (or a superuser) AFTER `nih init-db` and a
-- full pipeline/forecast run, with a password supplied by psql variable:
--
--   psql "$NIH_ADMIN_DSN" -v dashboard_password="$NIH_DASHBOARD_PASSWORD" \
--        -f scripts/create_readonly_role.sql
--
-- The role can SELECT the reporting marts, forecast outputs, pipeline
-- and monitoring status tables. It cannot insert, update, delete,
-- truncate, create objects, run ingestion, change alerts, or retrain
-- forecasts. The password is never stored in this repository.

\if :{?dashboard_password}
\else
  \echo 'Set -v dashboard_password=... (from your secret manager).'
  \quit
\endif

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'nih_dashboard') then
    create role nih_dashboard login;
  end if;
end
$$;

alter role nih_dashboard with password :'dashboard_password';
alter role nih_dashboard connection limit 5;
alter role nih_dashboard set statement_timeout = '15s';
alter role nih_dashboard set default_transaction_read_only = on;

grant connect on database nintendo_intel to nih_dashboard;
grant usage on schema mart_reported, mart_simulated, forecast, meta, ref to nih_dashboard;
grant select on all tables in schema mart_reported, mart_simulated, forecast to nih_dashboard;
grant select on meta.pipeline_runs, meta.monitoring_alerts,
    meta.monitoring_evaluations, meta.monitoring_alert_events to nih_dashboard;

-- dbt drops and recreates views on every build, which would silently
-- revoke direct grants. Default privileges keep future objects readable.
alter default privileges in schema mart_reported, mart_simulated, forecast
  grant select on tables to nih_dashboard;

-- Belt and braces: the demo role gets nothing in the raw schemas.
revoke all on schema raw_official, raw_simulated from nih_dashboard;
