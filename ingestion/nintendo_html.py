"""Parsers for Nintendo IR HTML pages.

Life-to-date pages stay on the life-to-date grain. A parenthetical combined
total is kept in the row note and is not turned into a second measure.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from html import unescape
from decimal import Decimal
from html.parser import HTMLParser

from ingestion.classify import normalize_label
from ingestion.numbers import parse_number
from ingestion.records import ParsedDocument, Rejection, StagedRow
from ingestion.vocabulary import TITLE_PAGE_PLATFORMS, family_platform
from nih.errors import NihError
from nih.periods import DisclosureMeasure, PeriodSpan, ProductGrain
from nih.provenance import SourceClass

_AS_OF = re.compile(
    r"As of\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MILLION = 1_000_000
_ALT_MEASURE = re.compile(
    r"""alt=(?P<quote>["'])Hardware:?\s*([0-9][0-9,.]*)\s+million\s+(?:units|pcs\.?)\s*/\s*Software:?\s*([0-9][0-9,.]*)\s+million\s+(?:units|pcs\.?)(?P=quote)""",
    re.IGNORECASE,
)
_ALT_NAME = re.compile(r"""alt=(["'])(?!Hardware:)([^"']+)\1""", re.IGNORECASE)
_TITLE_BLOCK = re.compile(
    r'<li class="sales_layout_list[^"]*">(.*?)</li>',
    re.IGNORECASE | re.DOTALL,
)
_TITLE = re.compile(r'<p class="sales_title">(.*?)</p>', re.IGNORECASE | re.DOTALL)
_VALUE = re.compile(
    r'<p class="sales_value">\s*<span>\s*([0-9][0-9,.]*)\s*</span>',
    re.IGNORECASE,
)
_NOTE = re.compile(r'<p class="sales_note">(.*?)</p>', re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


class HtmlParseError(NihError):
    """Raised when a downloaded page does not match the expected labels."""


def parse_as_of(html: str):
    match = _AS_OF.search(html)
    if match is None:
        raise HtmlParseError("The page does not print an 'As of' date.")
    month = _MONTHS.get(match.group(1).casefold())
    if month is None:
        raise HtmlParseError(f"Unrecognized month in the as-of date: {match.group(1)}")
    from datetime import date

    return date(int(match.group(3)), month, int(match.group(2)))


def parse_dedicated_units(
    html: str,
    *,
    source_url: str,
    retrieved_at: datetime,
    raw_filename: str,
) -> ParsedDocument:
    as_of = parse_as_of(html)
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    document = ParsedDocument(
        source_id="nintendo_dedicated_unit_sales",
        source_document_id=f"nintendo_dedicated_units_{as_of.isoformat()}",
        title="Dedicated video game sales units",
        source_url=source_url,
        publisher="Nintendo Co., Ltd.",
        published_on=as_of,
        period_label_verbatim=f"As of {as_of.isoformat()} life-to-date",
        raw_filename=raw_filename,
        content_sha256=digest,
        retrieved_at=retrieved_at,
    )
    found: dict[str, tuple[str, Decimal, Decimal]] = {}
    for name, hardware, software in _text_platforms(html):
        found[normalize_label(name)] = (name, hardware, software)
    for name, hardware, software in _alt_platforms(html):
        found.setdefault(normalize_label(name), (name, hardware, software))
    if not found:
        raise HtmlParseError("No hardware or software totals were found on the dedicated units page.")
    for name, hardware, software in found.values():
        mapped = family_platform(name)
        if mapped is None:
            document.rejections.append(
                Rejection(
                    document.source_document_id,
                    "unmapped_platform",
                    "The printed platform name has no warehouse code.",
                    platform_name=name,
                )
            )
            continue
        code, aggregate = mapped
        for metric, printed in (("hw_units_sell_in", hardware), ("sw_units_sell_in", software)):
            document.rows.append(
                _life_to_date_row(
                    document,
                    metric=metric,
                    platform_code=code,
                    platform_name=name,
                    aggregate=aggregate,
                    printed=printed,
                    game_code=None,
                    game_title=None,
                    product_grain=ProductGrain.HARDWARE if metric.startswith("hw_") else ProductGrain.SOFTWARE_TOTAL,
                    note=(
                        "Worldwide consolidated life-to-date sell-in printed on the "
                        "dedicated video game sales units page. Scale is million. "
                        f"Printed platform name: {name}."
                    ),
                )
            )
    return document


def parse_title_page(
    html: str,
    *,
    source_url: str,
    page_key: str,
    retrieved_at: datetime,
    raw_filename: str,
) -> ParsedDocument:
    mapped = TITLE_PAGE_PLATFORMS.get(page_key)
    if mapped is None:
        raise HtmlParseError(f"No platform is registered for title page {page_key}.")
    platform_code, aggregate = mapped
    as_of = parse_as_of(html)
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    document = ParsedDocument(
        source_id="nintendo_top_selling_titles",
        source_document_id=f"nintendo_top_titles_{page_key}_{as_of.isoformat()}",
        title=f"Top selling title sales units ({page_key})",
        source_url=source_url,
        publisher="Nintendo Co., Ltd.",
        published_on=as_of,
        period_label_verbatim=f"As of {as_of.isoformat()} life-to-date",
        raw_filename=raw_filename,
        content_sha256=digest,
        retrieved_at=retrieved_at,
    )
    titles = list(_title_blocks(html))
    if not titles:
        raise HtmlParseError(f"No title rows were found at {source_url}.")
    seen_codes: set[str] = set()
    for title, printed, note in titles:
        code = _game_code(title)
        if code in seen_codes:
            document.rejections.append(
                Rejection(
                    document.source_document_id,
                    "duplicate",
                    "The same title slug already appeared on this page.",
                    platform_name=platform_code,
                    printed_value=format(printed, "f"),
                )
            )
            continue
        seen_codes.add(code)
        definition = (
            "Worldwide consolidated life-to-date software sell-in for one printed title. "
            "Scale is million. Bundles and downloadable versions follow the page footnotes."
        )
        if note:
            definition = f"{definition} Page note: {note}"
        document.rows.append(
            _life_to_date_row(
                document,
                metric="sw_units_sell_in",
                platform_code=platform_code,
                platform_name=page_key,
                aggregate=aggregate,
                printed=printed,
                game_code=code,
                game_title=title,
                product_grain=ProductGrain.SOFTWARE_TITLE,
                note=definition,
            )
        )
    return document


def _life_to_date_row(
    document: ParsedDocument,
    *,
    metric: str,
    platform_code: str,
    platform_name: str,
    aggregate: bool,
    printed: Decimal,
    game_code: str | None,
    game_title: str | None,
    product_grain: ProductGrain,
    note: str,
) -> StagedRow:
    measure = DisclosureMeasure(
        source_document_id=document.source_document_id,
        source_class=SourceClass.OFFICIAL_IR,
        metric_code=metric,
        product_grain=product_grain,
        platform_code=platform_code,
        region_code="GLOBAL",
        game_code=game_code,
        fiscal_year_ending=None,
        period_span=PeriodSpan.LIFE_TO_DATE,
        fiscal_quarter=None,
        period_start=None,
        period_end=document.published_on,  # type: ignore[arg-type]
        as_of_date=document.published_on,  # type: ignore[arg-type]
        value=printed * _MILLION,
        is_forecast=False,
        is_additive_flow=True,
        is_platform_aggregate=aggregate,
        is_platform_component=False,
        parent_platform_code=None,
        is_region_aggregate=True,
        sales_basis="sell_in",
    )
    return StagedRow(
        measure=measure,
        printed_value=printed,
        scale_token="1000000",
        period_label_verbatim=document.period_label_verbatim,
        platform_name_verbatim=platform_name,
        region_name_verbatim="Worldwide",
        game_title=game_title,
        sheet_name="html",
        source_url=document.source_url,
        content_sha256=document.content_sha256,
        retrieved_at=document.retrieved_at,
        definition_note=note,
    )


class _DedicatedTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pairs: list[tuple[str, Decimal, Decimal]] = []
        self._capture: str | None = None
        self._name: str | None = None
        self._waiting_metric: str | None = None
        self._hardware: Decimal | None = None
        self._software: Decimal | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "")
        tokens = set(classes.split())
        if "hard_name" in tokens:
            self._capture = "name"
            self._buffer = []
        elif "num" in tokens:
            self._capture = "num"
            self._buffer = []
        elif "fs-g" in tokens:
            self._capture = "metric"
            self._buffer = []

    def handle_endtag(self, tag):
        if self._capture is None:
            return
        text = " ".join("".join(self._buffer).split())
        kind = self._capture
        self._capture = None
        self._buffer = []
        if kind == "name" and text:
            self._flush()
            self._name = text
        elif kind == "metric":
            folded = text.casefold()
            if folded.startswith("hardware"):
                self._waiting_metric = "hardware"
            elif folded.startswith("software"):
                self._waiting_metric = "software"
        elif kind == "num" and self._waiting_metric:
            number = parse_number(text)
            if number is None:
                return
            if self._waiting_metric == "hardware":
                self._hardware = number
            else:
                self._software = number
            self._waiting_metric = None
            if self._name and self._hardware is not None and self._software is not None:
                self._flush()

    def handle_data(self, data):
        if self._capture is not None:
            self._buffer.append(data)

    def close(self):
        super().close()
        self._flush()

    def _flush(self) -> None:
        if self._name and self._hardware is not None and self._software is not None:
            self.pairs.append((self._name, self._hardware, self._software))
        if self._name and (self._hardware is None) != (self._software is None):
            return
        self._hardware = None
        self._software = None


def _text_platforms(html: str) -> list[tuple[str, Decimal, Decimal]]:
    parser = _DedicatedTextParser()
    parser.feed(html)
    parser.close()
    return parser.pairs


def _alt_platforms(html: str) -> list[tuple[str, Decimal, Decimal]]:
    rows: list[tuple[str, Decimal, Decimal]] = []
    for match in _ALT_MEASURE.finditer(html):
        window = html[max(0, match.start() - 700) : match.start()]
        names = [item[1] for item in _ALT_NAME.findall(window)]
        if not names:
            continue
        name = " ".join(names[-1].split())
        hardware = parse_number(match.group(2))
        software = parse_number(match.group(3))
        if hardware is None or software is None:
            continue
        rows.append((name, hardware, software))
    return rows


def _title_blocks(html: str):
    for block in _TITLE_BLOCK.findall(html):
        title_match = _TITLE.search(block)
        value_match = _VALUE.search(block)
        if title_match is None or value_match is None:
            continue
        printed = parse_number(value_match.group(1))
        if printed is None:
            continue
        title = _plain(title_match.group(1))
        note_match = _NOTE.search(block)
        note = _plain(note_match.group(1)) if note_match else ""
        yield title, printed, note


def _plain(html: str) -> str:
    text = _TAG.sub(" ", unescape(html))
    return " ".join(text.split())


def _game_code(title: str) -> str:
    import unicodedata

    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.casefold()).strip("-")
    return (slug or "untitled")[:80]
