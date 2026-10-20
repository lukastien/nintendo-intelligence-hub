# Public data sources

`nih ingest` downloads public files, writes the bytes under `data/raw/nintendo/`, and writes parsed rows under `data/cleaned/nintendo/`. Those directories are gitignored. `nih init-db` does not insert official measures and does not invent them when a download fails.

Optional sources that are not configured are reported as unavailable. Their counts stay at zero.

## Official Nintendo IR

Publisher: Nintendo Co., Ltd. Host: `www.nintendo.co.jp`. These rows use `source_class = official_ir`.

| Source id | Page | What is parsed |
| --- | --- | --- |
| `nintendo_dedicated_unit_sales` | Dedicated video game sales units | Worldwide life-to-date hardware and software totals. The printed scale is million. |
| `nintendo_top_selling_titles` | Top selling title sales units, including the Switch, Wii U, and 3DS pages linked from the index | Worldwide life-to-date units for one printed title. A parenthetical combined total stays in the note. |
| `nintendo_historical_region_sales` | Historical data, consolidated sales workbook | Fiscal-year sell-in by region, plus the life-to-date column. The printed scale is ten thousand. |
| `nintendo_historical_income` | Historical data, consolidated income workbook | Full March 31 fiscal years for net sales, operating profit, ordinary profit, and profit attributable to owners of parent. The printed scale is millions of yen. |

The sales workbook's fiscal-year column is that year's sell-in. It is not a quarterly column and it is not life-to-date. The life-to-date column is stored with an empty fiscal year. `Q1-Q3` would be stored as the April-December cumulative. A bare `Q3` would be the October-December quarter. The historical workbooks do not contain those quarterly headers.

These printed columns are rejected instead of being relabeled:

- `FY3/2015~` and `FY3/2024 ~`, because the tilde marks an open-ended bucket
- `FY8/YYYY`, because those years ended in August
- `FY3/1990` on the income sheet, because Nintendo's note says that period is seven months
- Ratio rows and statement lines that have no metric code
- Platform names that are not in the ingestion vocabulary

Blank cells stay missing. They are not stored as zero.

### Manual files

If a download fails, the loader looks in `data/raw/manual/<source_id>/`.

| Source id | Expected file |
| --- | --- |
| `nintendo_dedicated_unit_sales` | One `.html` file |
| `nintendo_top_selling_titles` | `switch2.html`, `switch.html`, `wiiu.html`, `3ds.html` |
| `nintendo_historical_region_sales` | One `.xlsx` file whose name ends in Nintendo's `eYYMM` suffix |
| `nintendo_historical_income` | One `.xls` file with the same suffix |

The suffix supplies the as-of month only when the historical index page itself could not be read. A downloaded index page must agree with the file suffix.

## Not ingested

The dedicated "Unit Sales" tab is an Euroland chart in an iframe. It is not a Nintendo file with a stable document hash, so it is not scraped.

Financial-results PDFs are not parsed. A misread PDF table would invent a period span. Those documents remain a later, reviewed transcription.

Third-party chart sites are not downloaded. Their redistribution terms are not a license this repository can apply, and their figures are not Nintendo sell-in.

## IGDB

Source id: `igdb_game_metadata`. Class: `public_reference`. This source is game names and release timestamps, not unit sales.

Set both environment variables to a Twitch application:

```bash
NIH_IGDB_CLIENT_ID=
NIH_IGDB_CLIENT_SECRET=
```

If either one is empty, IGDB is unavailable and no titles are invented. A failed API call is reported and does not write official facts.

## Licensed public file

Source id: `licensed_public_sales`. Nothing is bundled.

Create `data/raw/manual/licensed_public_sales/manifest.yaml`:

```yaml
license_name: Name of the license
license_url: https://example.invalid/license
source_url: https://example.invalid/dataset
file: sales.csv
```

`sales.csv` needs the columns `title`, `platform`, `region`, `period_label`, `units`, and `measurement_type`. Blank `units` are counted as missing. These rows are written under `data/cleaned/public_reference/` and are not loaded into `raw_official`.
