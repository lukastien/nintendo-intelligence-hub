# Production readiness audit — Phase 8

Date: 2026-10-20. Scope: the whole repository at the Phase 7 commit.

## Secrets and credentials

| Check | Result |
| --- | --- |
| Tracked `.env` | None. Only `.env.example` (placeholders) is tracked |
| `.gitignore` coverage | `.env`, `.streamlit/secrets.toml`, raw/cleaned/export data, dbt target/logs all ignored |
| Secret patterns in tracked files | None found (Slack webhook URLs, private keys, cloud access keys, hardcoded password assignments) |
| Git history (6 commits) | No `.env`, key, or secrets file ever committed; pattern scan of history clean |
| Notification credentials | Environment only (`NIH_SLACK_WEBHOOK_URL`, `NIH_SMTP_*`); never logged |
| Database password default | `nih_local_only` default in `nih/config.py` is a local-development default matching docker-compose; deployments must override via `NIH_POSTGRES_PASSWORD` |

**Not claimed:** history rewriting. None was needed — no secret was
ever committed, so there is nothing to remediate. If a credential is
ever committed in future, rotate it first; rewriting history alone
does not un-leak a secret.

## SQL safety

All value binding is parameterized. The only f-string SQL interpolates
**table identifiers from hardcoded internal tuples**
(`nih/pipeline.py` mart counts, `monitoring/engine.py` mart counts and
alert-filter fragments, `warehouse/load.py` table names from the load
registry). No user input reaches those strings; CLI arguments are bound
as parameters or validated as integers. Dashboard queries in
`dashboards/queries.py` are fully parameterized.

## Generated files

Raw downloads, cleaned CSVs, Tableau exports, dbt target, and the
forecast/monitoring database contents are runtime artifacts, ignored
by git. The repository ships code, DDL, seeds, tests, and docs.

## Failure handling

- Dashboard: database-unavailable state stops with instructions rather
  than showing substitute figures; per-page query failures surface as
  warnings with the exception text.
- Pipeline: advisory lock, exit codes 0/1/2 by failure class, failed
  runs recorded with a critical monitoring alert.
- Forecasting/monitoring: model fit failures are counted and stored;
  rule failures fail the evaluation visibly.
- Public demo separation: `nih_dashboard` read-only role (SELECT on
  marts/forecast/monitoring status, 15s statement timeout, raw schemas
  revoked) verified locally — writes raise `ReadOnlySqlTransaction`,
  raw reads raise `InsufficientPrivilege`. The dashboard has no code
  path that triggers ingestion, alert mutation, or model training.

## Performance notes

Dashboard queries are cached (`st.cache_data`, 120–300s TTL) and read
pre-aggregated marts; the largest mart read is ~2k rows. Forecast and
monitoring pages read only stored run outputs. No per-refresh training
or ingestion occurs.

## Outstanding items

See `docs/DEPLOYMENT_CHECKLIST.md`. The application is **not** publicly
deployed: no cloud database or Streamlit Cloud app has been created,
because both need the owner's accounts. Everything required to deploy
is prepared and locally verified.
