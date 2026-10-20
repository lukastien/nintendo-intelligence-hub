# Deployment

Local execution and GitHub Actions are different jobs. Only a durable database keeps official rows after the process exits.

## Run locally

```bash
docker compose up -d --wait
nih init-db
python -m nih pipeline run
python -m nih pipeline status
python -m nih pipeline history
```

Configuration comes from `config/settings.yaml`, then `.env`, then `NIH_*` environment variables. `.env` is gitignored. The local password in `.env.example` is the Docker Compose default, not a production secret.

`NIH_POSTGRES_SSLMODE` is optional. Leave it unset for the local container. Set it to `require` when the durable host asks for TLS.

Logs are the command's stderr. The durable record is `meta.pipeline_runs`.

## Public demo deployment (recommended architecture)

**Streamlit Community Cloud (app) + a managed free-tier PostgreSQL
(Neon or Supabase) holding a restored copy of the local warehouse,
accessed through the read-only `nih_dashboard` role.**

Why this shape:

- The local Docker PostgreSQL is unreachable from any cloud host, and
  CI databases are destroyed with the runner — the demo needs a
  durable, network-reachable database. A managed free tier is the
  lowest-cost durable option.
- Streamlit Community Cloud is free, deploys from GitHub, and stores
  credentials in its secrets manager (the app maps `st.secrets` to
  `NIH_*` environment variables at startup).
- The read-only role (verified locally: writes raise
  `ReadOnlySqlTransaction`, raw schemas revoked, 15s statement
  timeout) means a public visitor cannot trigger ingestion, modify
  alerts, retrain forecasts, or read credentials — the dashboard has
  no such code paths anyway.
- Tradeoffs: free-tier databases sleep/scale-to-zero (first query can
  be slow), Streamlit Cloud resources are modest, and the demo data is
  a snapshot — refreshing it means re-dumping locally and restoring,
  which is appropriate for a portfolio. Self-hosting (a VPS running
  Docker Compose) avoids snapshot staleness but adds cost, patching,
  TLS, and uptime work; it is not recommended for this purpose.

### Exact manual steps (owner accounts required — not yet done)

1. Create a free Neon (or Supabase) project; note host, port, database.
2. From this repo, dump the local warehouse:
   `docker compose exec -T postgres pg_dump -U nih -d nintendo_intel > nih_demo.sql`
   (or `pg_dump` against `localhost:54329`).
3. Restore into the managed database with its admin connection, then
   create the demo role there:
   `psql "<managed-admin-dsn>" -v dashboard_password="<strong-password>" -f scripts/create_readonly_role.sql`
4. Push this repository to GitHub (already the origin remote).
5. On Streamlit Community Cloud: New app → this repo → main file
   `dashboards/app.py`. In **Secrets**, set `NIH_POSTGRES_HOST`,
   `NIH_POSTGRES_PORT`, `NIH_POSTGRES_DB`, `NIH_POSTGRES_USER`
   (`nih_dashboard`), `NIH_POSTGRES_PASSWORD`, `NIH_POSTGRES_SSLMODE`
   (`require`).
6. Deploy, open the app URL in a private window, click through all six
   pages, and confirm figures load. Only then add the URL to README.md.

Nothing above has been executed: no external account was created and
no URL exists yet. Do not describe the demo as live until step 6
passes.

## Continuous integration

`.github/workflows/ci.yml` runs on push and pull request. It installs the package, starts a temporary PostgreSQL 16 service, runs `nih init-db`, `pytest`, and `dbt build`. That database is destroyed with the runner. A green CI job does not mean official Nintendo rows were saved anywhere.

CI does not call `pipeline run`, because that command downloads IR files and would write them only into the temporary service.

## Scheduled ingestion

`.github/workflows/scheduled-ingestion.yml` is `workflow_dispatch` plus a Monday schedule. It does not start PostgreSQL. The job exits 1 when `NIH_POSTGRES_HOST` is missing, and it tells the operator to disable the workflow until a durable host exists.

Secrets, set in the GitHub repository and never committed:

| Secret | Required |
| --- | --- |
| `NIH_POSTGRES_HOST` | Yes, for a real ingestion run |
| `NIH_POSTGRES_PORT` | Yes |
| `NIH_POSTGRES_DB` | Yes |
| `NIH_POSTGRES_USER` | Yes |
| `NIH_POSTGRES_PASSWORD` | Yes |
| `NIH_POSTGRES_SSLMODE` | When the host requires TLS |
| `NIH_IGDB_CLIENT_ID` | No. Empty means IGDB stays a warning |
| `NIH_IGDB_CLIENT_SECRET` | No |

GitHub-hosted runners cannot reach the Docker database on a laptop. They also cannot reach a private network address. A persistent run needs a host that accepts connections from GitHub, or a self-hosted runner on the same network as the database.

Disabling the workflow in the GitHub Actions UI is the right state until those secrets point at a database you intend to keep.

## What a cloud deployment still needs

This repository does not provision a cloud warehouse. A durable deployment would add:

- A PostgreSQL instance with backups, and a network path from the runner.
- The `NIH_POSTGRES_*` secrets above, plus TLS when the provider requires it.
- A decision to keep `NIH_WAREHOUSE_TARGET=postgres`. BigQuery is still fail-closed without a project id, and this pipeline does not load it.
- Alerts on `pipeline status` when the latest run is failed or a publication window is overdue. The table to query is `meta.pipeline_runs`.
- Retention for `data/raw` if the runner's disk is ephemeral. The checksum and facts live in PostgreSQL; the raw bytes on the runner do not survive unless they are copied to object storage.

The marts are views. After a successful load, `dbt build` on that same database refreshes them. A second runner pointed at a different database does not see the first runner's rows.
