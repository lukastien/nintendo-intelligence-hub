# Demo script (2–3 minutes)

Setup: `streamlit run dashboards/app.py` against the local warehouse.
Have a terminal ready with `python -m nih pipeline status`.

## 0:00 — Framing (Executive Overview)

"This is Nintendo Intelligence Hub — an end-to-end BI system over
genuine Nintendo investor-relations data. Everything on screen is
queried live from PostgreSQL; no figure is typed into the dashboard."
Point at the disclaimer and the data-volume captions.

## 0:30 — The analytical trap (Hardware & Software)

Pick the Switch family. "A family total already includes its component
models — Switch Lite is inside this number, not added to it. The mart
enforces that with an inclusion flag, and dbt tests fail the build if
it is violated." Switch to a retired platform and note annual flows
are never mixed with life-to-date snapshots.

## 1:00 — Regional honesty (Regional Performance)

Show a regional view. "Older workbooks print a different regional
layout — Europe inside Other. The marts never combine layouts, and
where regional parts and the disclosed worldwide total differ beyond
reporting precision, monitoring flags it instead of silently replacing
either number."

## 1:30 — Operations (Pipeline Health)

Show the monitoring panel: health pill, severity counts, the four
regional warnings. "Monitoring runs after every pipeline build.
Alerts are deduplicated by fingerprint — running it twice creates
zero duplicates — and each one explains itself: metric, period,
baseline, rule." In the terminal: `python -m nih monitor status`.

## 2:00 — Forecasting, honestly (Predictive Analytics)

Open Switch software. "Nine models were backtested over expanding
windows — training never sees the target year. The winner here is a
simple smoothing model; on consolidated sales the naive forecast
actually wins, and we report that. The interval is a normal
approximation over backtest errors — historical coverage was 63%
against an 80% band, and the page says so." Switch the selector to a
3DS series to show the end-of-life warning.

## 2:30 — Engineering challenge

"My favourite defect: Nintendo's Q1–Q3 columns are April-to-December
cumulative totals, not quarters. The warehouse stores the printed
span and derives a quarter only by subtracting the previous YTD span —
and because no quarterly source columns are loaded, the quarterly
marts are correctly empty rather than fabricated."

Close: "100 Python tests, 72 dbt checks, zero hardcoded figures. The
case study in the repo walks through every decision."
