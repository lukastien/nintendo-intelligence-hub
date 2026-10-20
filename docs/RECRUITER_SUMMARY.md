# Nintendo Intelligence Hub — Recruiter Summary

Nintendo Intelligence Hub is an end-to-end business intelligence
system built on genuine Nintendo investor-relations disclosures. A
Python ETL pipeline loads 2,323 official records (unit sales by
platform and region, consolidated financials back to FY3/1991) into
PostgreSQL, where dbt builds five tested analytics marts. On top sit
three analytical layers: a six-page Streamlit dashboard that queries
the warehouse live, a monitoring system that detects data-quality
problems and unusual annual movements with deduplicated, auditable
alerts, and a forecasting job that backtests nine models over
expanding windows and reports honest accuracy — including when the
naive forecast wins.

The engineering emphasis is correctness under real reporting traps:
cumulative spans that are not quarters, platform families that already
include their component models, changing regional definitions, and
legitimate negative disclosed values. Safeguards are enforced by dbt
tests and 100 Python tests, not by convention. The system is
deployment-ready — a verified read-only demo role and cloud
instructions are prepared — but is not yet publicly hosted, pending
the owner's cloud accounts. It is an independent portfolio project,
not affiliated with Nintendo.
