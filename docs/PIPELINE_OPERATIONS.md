# Pipeline operations

The orchestrated command is:

```bash
python -m nih pipeline run
```

`nih pipeline run` is the same command. It needs the local PostgreSQL warehouse from `docker compose up -d --wait` and `nih init-db`.

The run does ten steps:

1. Load configuration and confirm the target is PostgreSQL.
2. Open the database and take a session lock so a second run stops instead of writing at the same time.
3. Discover the source catalog.
4. Download each selected source, or read a manual file when the download fails and a file is already in `data/raw/manual/`.
5. Parse the file. Invalid periods and unmapped labels become rejections, not guessed rows.
6. Load official rows. A matching file checksum leaves that document's rows in place. A new or corrected checksum replaces only that document.
7. Run the warehouse purity audit.
8. Run `dbt build`.
9. Query the five official marts, the two quarterly marts, and the simulated mart.
10. Write `meta.pipeline_runs`.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Mandatory sources loaded, the audit passed, dbt succeeded, and the marts were queryable |
| 1 | A mandatory source, audit, dbt build, or mart check failed |
| 2 | Configuration is unusable, PostgreSQL is unreachable, or another run holds the lock |

Optional IGDB and licensed-file gaps print as `warning:` and do not change the exit code. They do not create substitute rows.

## Repeat a run

Run the same command again. Unchanged Nintendo files are counted as `unchanged`. Official fact tables do not gain duplicate rows. `nih ingest` uses the same checksum load and the same lock, but it does not run dbt or write `meta.pipeline_runs`.

`--source` limits the run to named source ids. Sources that are not selected are left as they are. `--skip-dbt` loads and audits without `dbt build`. The mart check runs only after a successful dbt build.

## Inspect a run

```bash
python -m nih pipeline history
python -m nih pipeline history --limit 5
python -m nih pipeline status
```

History lists recent executions, including failed ones. Status shows the latest run, the newest official as-of date, and outstanding issues.

Annual workbook freshness uses the March 31 fiscal close plus 90 days. Quarterly IR pages use the latest fiscal quarter-end that is at least 45 days old. A file inside that window is current. It is not marked stale for being older than a day. Retired-platform title pages are not judged on their own; the newest page in that group is.

An empty quarterly mart is reported as expected. It becomes a failure only when the view itself cannot be queried, or when official facts are loaded and an annual, lifetime, regional, trend, or financial mart is empty.

## Logs

The CLI writes structured lines to stderr:

```text
2026-10-20T17:00:00 INFO nih.pipeline source_finished source_id=nintendo_historical_income status=loaded inserted=0 updated=0 unchanged=144
```

Search for `pipeline_started`, `source_finished`, `optional_source_warning`, `warehouse_audit_failed`, `dbt_failed`, and `pipeline_finished`.

## Diagnose a failure

| Symptom | What to do |
| --- | --- |
| Exit 2 and "not reachable" | Start PostgreSQL and check `NIH_POSTGRES_*` in `.env` |
| Exit 2 and "already executing" | Wait for the other `pipeline run` or `nih ingest` to finish. The lock is released when that process exits |
| Exit 1 and a source "unavailable" | The download failed and no manual file was present. Previously loaded rows for that document are still in the warehouse. Restore the network, or place the official file under `data/raw/manual/<source_id>/`, then rerun |
| Exit 1 and a source "failed" | The file was retrieved but could not be parsed. The previous document was not deleted. Fix or replace the file and rerun |
| `dbt_status=failed` | Read the error tail printed by the command. The load may already have committed. Rerun the same command; unchanged documents are not duplicated, and dbt runs again |
| `validation_failures` and a purity message | Official and simulated rows were mixed, or the entity check failed. Do not publish the marts until the audit is clean |
| A run left at `running` | The process stopped before it could finish. The next run that acquires the lock marks that row failed and interrupted |

Rerun the whole pipeline with `python -m nih pipeline run`. To rebuild marts after a dbt-only failure, the same command is the rerun. There is no separate repair command.

## What a run does not do

It does not delete official rows because a remote host is down. It does not fill a gap with the synthetic weekly series. It does not manufacture quarterly values. It does not deploy a dashboard.
