# Deployment checklist

## Local (verified 2026-10-20)

- [x] Full pytest suite green (see README testing section)
- [x] `dbt build` green
- [x] `python -m nih pipeline status` / `monitor status` / `forecast status` succeed
- [x] Official counts unchanged: 2,179 unit rows, 144 financial rows, 48 synthetic rows; marts 1,968 / 1,483 / 691 / 175 / 36
- [x] Read-only `nih_dashboard` role created locally and proven: mart/forecast reads work, writes blocked, raw schemas blocked
- [x] Tableau exports regenerated and row-count verified
- [x] Secret scan of tracked files and git history clean; `.env` untracked
- [x] Dashboard smoke-tested on all six pages (browser + AppTest)
- [x] No credentials in the repository; notification secrets env-only

## Public demo (manual — requires the owner's accounts)

- [ ] Create free-tier managed PostgreSQL (Neon or Supabase)
- [ ] `pg_dump` the local warehouse and restore it into the managed database
- [ ] Run `scripts/create_readonly_role.sql` against the managed database with a strong password from a password manager
- [ ] Create the Streamlit Community Cloud app from this GitHub repo (`dashboards/app.py`)
- [ ] Set the six `NIH_POSTGRES_*` secrets (user = `nih_dashboard`, SSL `require`)
- [ ] Open the deployed URL in a private window; verify all six pages load and the disclaimer shows
- [ ] Confirm the demo cannot write: the role is read-only and the app exposes no ingestion/alert/forecast actions
- [ ] Add the verified URL to README.md and `docs/RECRUITER_SUMMARY.md`
- [ ] Optional: publish the Tableau workbook via `docs/TABLEAU_BUILD_GUIDE.md` and link it

## Never do

- Never point a public app at the local Docker PostgreSQL.
- Never expose PostgreSQL publicly without the read-only role, TLS, and a strong password.
- Never commit `.env`, `secrets.toml`, or a database dump containing credentials.
- Never describe the demo as live before the URL has been opened and tested.
