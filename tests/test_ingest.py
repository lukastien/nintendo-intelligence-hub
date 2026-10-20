"""Ingestion tests use invented fixtures. They do not call Nintendo or IGDB."""

import csv
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import requests

from ingestion.classify import classify_period_header
from ingestion.http import FetchError, get_bytes
from ingestion.licensed import licensed_outcome
from ingestion.nintendo_html import parse_dedicated_units, parse_title_page
from ingestion.nintendo_workbook import parse_income_grid, parse_sales_workbook
from ingestion.pipeline import genuine_official_count, run_ingestion
from nih.cli import main
from nih.periods import PeriodSpan


def test_period_headers_keep_cumulative_and_quarter_labels_apart():
    cumulative = classify_period_header("Q1-Q3")
    quarter = classify_period_header("Q3")
    assert cumulative is not None and cumulative.accepted
    assert cumulative.period_span is PeriodSpan.Q1_Q3
    assert cumulative.fiscal_quarter is None
    assert quarter is not None and quarter.accepted
    assert quarter.period_span is PeriodSpan.QUARTER
    assert quarter.fiscal_quarter == 3
    assert classify_period_header("FY3/2098").period_span is PeriodSpan.FISCAL_YEAR
    assert classify_period_header("Life\nto date").period_span is PeriodSpan.LIFE_TO_DATE
    assert classify_period_header("FY3/2099~").accepted is False
    assert classify_period_header("FY8/2090").reason == "august_fiscal_year"


def test_fetch_retries_then_returns_the_body():
    class Session:
        def __init__(self):
            self.calls = 0

        def get(self, url, headers, timeout):
            self.calls += 1
            if self.calls < 3:
                raise requests.ConnectionError("down")

            class Response:
                status_code = 200
                content = b"official-bytes"

            return Response()

        def close(self):
            return None

    session = Session()
    body = get_bytes("https://example.invalid/file", attempts=3, sleep=lambda _seconds: None, session=session)
    assert body == b"official-bytes"
    assert session.calls == 3


def test_fetch_stops_after_the_retry_budget():
    class Session:
        def __init__(self):
            self.calls = 0

        def get(self, url, headers, timeout):
            self.calls += 1

            class Response:
                status_code = 503
                content = b""

            return Response()

        def close(self):
            return None

    session = Session()
    with pytest.raises(FetchError):
        get_bytes("https://example.invalid/file", attempts=3, sleep=lambda _seconds: None, session=session)
    assert session.calls == 3


def test_dedicated_page_is_life_to_date_million_scale():
    html = """
    <div class="sinf_date">( As of June 30, 2099 )</div>
    <p class="hard_name">Nintendo Switch 2</p>
    <p class="data">
      <span class="fs-g">Hardware:</span><span class="num">1.5</span><span class="unit">million pcs.</span>
      <span class="fs-g">Software:</span><span class="num">2.25</span><span class="unit">million pcs.</span>
    </p>
    <img alt="Wii" src="a.png">
    <img alt="Hardware: 3 million pcs. / Software: 4 million pcs." src="b.png">
    """
    document = parse_dedicated_units(
        html,
        source_url="https://www.nintendo.co.jp/ir/en/finance/hard_soft/index.html",
        retrieved_at=_retrieved(),
        raw_filename="dedicated.html",
    )
    by_platform = {(row.measure.platform_code, row.measure.metric_code): row for row in document.rows}
    hardware = by_platform[("NS2", "hw_units_sell_in")]
    assert hardware.measure.period_span is PeriodSpan.LIFE_TO_DATE
    assert hardware.measure.fiscal_year_ending is None
    assert hardware.measure.value == Decimal("1500000")
    assert hardware.measure.region_code == "GLOBAL"
    assert by_platform[("WII", "sw_units_sell_in")].measure.value == Decimal("4000000")


def test_title_page_keeps_the_printed_title_and_not_the_parenthetical():
    html = """
    <div class="sinf_date">( As of June 30, 2099 )</div>
    <li class="sales_layout_list">
      <p class="sales_title">Example<br>Kart</p>
      <p class="sales_value"><span>1.25</span> million pcs.</p>
      <p class="sales_note">(Combined with another edition, total sales reach 9 million pcs.)</p>
    </li>
    """
    document = parse_title_page(
        html,
        source_url="https://www.nintendo.co.jp/ir/en/finance/software/index.html",
        page_key="switch2",
        retrieved_at=_retrieved(),
        raw_filename="titles.html",
    )
    assert len(document.rows) == 1
    row = document.rows[0]
    assert row.game_title == "Example Kart"
    html_entity = """
    <div class="sinf_date">( As of June 30, 2099 )</div>
    <li class="sales_layout_list ta_center">
      <p class="sales_title">Pok&eacute;mon Example</p>
      <p class="sales_value"><span>2</span> million pcs.</p>
    </li>
    """
    entity_document = parse_title_page(
        html_entity,
        source_url="https://www.nintendo.co.jp/ir/en/finance/software/3ds.html",
        page_key="3ds",
        retrieved_at=_retrieved(),
        raw_filename="3ds.html",
    )
    assert entity_document.rows[0].game_title == "Pokémon Example"
    assert entity_document.rows[0].measure.game_code == "pokemon-example"
    assert row.measure.game_code == "example-kart"
    assert row.measure.value == Decimal("1250000")
    assert row.measure.period_span is PeriodSpan.LIFE_TO_DATE
    assert "9 million" not in format(row.measure.value, "f")
    assert "Combined with another edition" in row.definition_note


def test_sales_workbook_separates_fiscal_year_life_to_date_and_blanks(tmp_path):
    path = tmp_path / "sales.xlsx"
    _write_sales_fixture(path)
    document = parse_sales_workbook(
        path,
        source_url="https://www.nintendo.co.jp/ir/en/finance/historical_data/index.html",
        as_of=date(2099, 3, 31),
        retrieved_at=_retrieved(),
        raw_filename="sales.xlsx",
    )
    flows = [
        row
        for row in document.rows
        if row.measure.period_span is PeriodSpan.FISCAL_YEAR
        and row.measure.platform_code == "NSW_FAMILY"
        and row.measure.metric_code == "hw_units_sell_in"
        and row.measure.region_code == "JPN"
    ]
    assert len(flows) == 1
    assert flows[0].measure.fiscal_year_ending == 2098
    assert flows[0].measure.period_start == date(2097, 4, 1)
    assert flows[0].measure.period_end == date(2098, 3, 31)
    assert flows[0].measure.value == Decimal("100000")
    lite = next(row for row in document.rows if row.measure.platform_code == "NSLITE")
    assert lite.measure.is_platform_component is True
    assert lite.measure.parent_platform_code == "NSW_FAMILY"
    assert lite.measure.period_span is PeriodSpan.LIFE_TO_DATE
    other = next(row for row in document.rows if row.measure.region_code == "OTH_INCL_EUROPE")
    assert "includes Europe" in other.definition_note
    split_other = next(row for row in document.rows if row.measure.platform_code == "WIIU" and row.measure.region_code == "OTH")
    assert split_other.measure.value == Decimal("40000")
    assert document.missing_cells >= 1
    assert any(item.reason == "open_ended_column" for item in document.rejections)
    assert any(item.reason == "unmapped_platform" for item in document.rejections)
    assert all(row.measure.platform_code != "MYSTERY" for row in document.rows)


def test_income_grid_rejects_august_years_stub_years_and_ratios():
    grid = [
        ["Nintendo Co., Ltd."],
        ["(In millions of yen)"],
        ["", "FY8/2090", "FY3/1990", "FY3/2098"],
        ["Net sales", 5, 6, 7],
        ["(Gross profit ratio)", 0.2, 0.3, 0.4],
        ["Gross profit", 1, 1, 1],
        ["The period of FY3/1990 is 7 months."],
    ]
    document = parse_income_grid(
        grid,
        source_url="https://www.nintendo.co.jp/ir/en/finance/historical_data/index.html",
        as_of=date(2098, 3, 31),
        retrieved_at=_retrieved(),
        raw_filename="income.xls",
        content_sha256="abc",
    )
    assert len(document.rows) == 1
    row = document.rows[0]
    assert row.measure.metric_code == "net_sales_jpy"
    assert row.measure.period_span is PeriodSpan.FISCAL_YEAR
    assert row.measure.fiscal_year_ending == 2098
    assert row.measure.value == Decimal("7000000")
    assert row.scale_token == "millions"
    reasons = {item.reason for item in document.rejections}
    assert "august_fiscal_year" in reasons
    assert "seven_month_stub" in reasons
    assert "not_a_level" in reasons
    assert "unmapped_metric" in reasons


def test_failed_download_writes_no_substitute_rows(tmp_path):
    def explode(_url: str) -> bytes:
        raise FetchError("network down")

    outcomes = run_ingestion(
        ["nintendo_dedicated_unit_sales", "igdb_game_metadata", "licensed_public_sales"],
        fetcher=explode,
        output_root=tmp_path,
        load_warehouse=False,
        retrieved_at=_retrieved(),
    )
    assert [outcome.status for outcome in outcomes] == ["unavailable", "unavailable", "unavailable"]
    assert genuine_official_count(outcomes) == 0
    written = list(tmp_path.rglob("*"))
    assert written == [] or all(path.stat().st_size == 0 for path in written if path.is_file())
    assert not any("synthetic" in path.name for path in written)


def test_licensed_manifest_is_required_and_blank_units_stay_missing(tmp_path):
    missing = licensed_outcome(tmp_path)
    assert missing.status == "unavailable"
    assert missing.accepted == 0
    folder = tmp_path / "raw" / "manual" / "licensed_public_sales"
    folder.mkdir(parents=True)
    (folder / "sales.csv").write_text(
        "title,platform,region,period_label,units,measurement_type\nExample,NS2,GLOBAL,FY3/2098,12,shipments\nBlank,NS2,GLOBAL,FY3/2098,,shipments\n",
        encoding="utf-8",
    )
    (folder / "manifest.yaml").write_text(
        "license_name: Example License\nlicense_url: https://example.invalid/license\nsource_url: https://example.invalid/data\nfile: sales.csv\n",
        encoding="utf-8",
    )
    loaded = licensed_outcome(tmp_path)
    assert loaded.status == "loaded"
    assert loaded.accepted == 1
    assert loaded.missing == 1


def test_manual_title_files_keep_the_official_page_url(tmp_path):
    folder = tmp_path / "raw" / "manual" / "nintendo_top_selling_titles"
    folder.mkdir(parents=True)
    html = """
    <div class="sinf_date">( As of June 30, 2099 )</div>
    <li class="sales_layout_list">
      <p class="sales_title">Manual Example</p>
      <p class="sales_value"><span>1.5</span> million pcs.</p>
    </li>
    """
    (folder / "switch2.html").write_text(html, encoding="utf-8")
    (folder / "switch.html").write_text(html, encoding="utf-8")

    def offline(_url: str) -> bytes:
        raise FetchError("offline")

    outcomes = run_ingestion(
        ["nintendo_top_selling_titles"],
        fetcher=offline,
        output_root=tmp_path,
        load_warehouse=False,
        retrieved_at=_retrieved(),
    )
    assert outcomes[0].status == "loaded"
    assert outcomes[0].accepted == 2
    urls = set()
    for path in (tmp_path / "cleaned" / "nintendo").glob("nintendo_top_titles_*.csv"):
        if path.name.endswith("_rejected.csv"):
            continue
        with path.open(encoding="utf-8") as handle:
            urls.add(next(csv.DictReader(handle))["source_url"])
    assert urls == {
        "https://www.nintendo.co.jp/ir/en/finance/software/index.html",
        "https://www.nintendo.co.jp/ir/en/finance/software/switch.html",
    }
    assert all(url.startswith("https://www.nintendo.co.jp/") for url in urls)


def test_ingest_command_reports_an_unconfigured_optional_source(capsys):
    assert main(["ingest", "--source", "licensed_public_sales", "--skip-warehouse"]) == 0
    output = capsys.readouterr().out
    assert "licensed_public_sales: unavailable" in output
    assert "genuine official records accepted: 0" in output


def _retrieved() -> datetime:
    return datetime(2099, 4, 1, tzinfo=timezone.utc)


def _write_sales_fixture(path) -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Family"
    sheet["A1"] = "units in ten thousands"
    sheet["D2"] = "FY3/2098"
    sheet["E2"] = "FY3/2099~"
    sheet["F2"] = "Life to date"
    sheet["A3"] = "Nintendo Switch"
    sheet["B3"] = "Hardware"
    sheet["C3"] = "Japan"
    sheet["D3"] = 10
    sheet["E3"] = 2
    sheet["F3"] = 40
    sheet["C4"] = "The Americas"
    sheet["E4"] = 1
    sheet["F4"] = 5
    sheet["B5"] = "of which Nintendo Switch Lite"
    sheet["C5"] = "Japan"
    sheet["F5"] = 3
    sheet["B6"] = "Software"
    sheet["C6"] = "Total"
    sheet["D6"] = 4
    sheet["F6"] = 9
    sheet["C7"] = "Other"
    sheet["D7"] = 6
    sheet["A8"] = "Mystery Box"
    sheet["B8"] = "Hardware"
    sheet["C8"] = "Japan"
    sheet["D8"] = 7
    europe = workbook.create_sheet("Split")
    europe["A1"] = "units in ten thousands"
    europe["D2"] = "FY3/2098"
    europe["A3"] = "Wii U"
    europe["B3"] = "Hardware"
    europe["C3"] = "Europe"
    europe["D3"] = 3
    europe["C4"] = "Other"
    europe["D4"] = 4
    workbook.save(path)
