"""Download public sources, parse them, and optionally load PostgreSQL."""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from ingestion.http import FetchError, get_bytes
from ingestion.igdb import igdb_outcome
from ingestion.licensed import licensed_outcome
from ingestion.nintendo_html import HtmlParseError, parse_dedicated_units, parse_title_page
from ingestion.nintendo_workbook import (
    WorkbookParseError,
    as_of_from_filename,
    discover_historical_files,
    parse_income_workbook,
    parse_sales_workbook,
)
from ingestion.records import (
    CLEANED_COLUMNS,
    ParsedDocument,
    SourceOutcome,
    cleaned_record,
    dedupe_rows,
)
from ingestion.registry import load_source_catalog
from nih.config import project_root
from nih.errors import NihError

logger = logging.getLogger("nih.ingest")

OFFICIAL_SOURCES = (
    "nintendo_dedicated_unit_sales",
    "nintendo_historical_region_sales",
    "nintendo_historical_income",
    "nintendo_top_selling_titles",
)
OPTIONAL_SOURCES = ("igdb_game_metadata", "licensed_public_sales")
ALL_SOURCES = OFFICIAL_SOURCES + OPTIONAL_SOURCES

Fetcher = Callable[[str], bytes]


def run_ingestion(
    selected: list[str] | None = None,
    *,
    fetcher: Fetcher | None = None,
    output_root: Path | None = None,
    load_warehouse: bool = True,
    retrieved_at: datetime | None = None,
) -> list[SourceOutcome]:
    """Ingest the requested sources.

    Official Nintendo files are parsed into cleaned rows. IGDB and a licensed
    third-party file are optional. A failed download does not create rows.
    """

    chosen = list(selected or ALL_SOURCES)
    unknown = sorted(set(chosen) - set(ALL_SOURCES))
    if unknown:
        raise NihError(f"Unknown ingestion source: {', '.join(unknown)}")
    root = output_root or project_root() / "data"
    fetch = fetcher or get_bytes
    moment = retrieved_at or datetime.now(timezone.utc)
    catalog = {source.source_id: source for source in load_source_catalog()}
    outcomes: list[SourceOutcome] = []
    documents: list[ParsedDocument] = []

    if "nintendo_dedicated_unit_sales" in chosen:
        outcome, parsed = _dedicated(catalog, fetch, root, moment)
        outcomes.append(outcome)
        documents.extend(parsed)
    if "nintendo_historical_region_sales" in chosen or "nintendo_historical_income" in chosen:
        outcomes.extend(_historical(chosen, catalog, fetch, root, moment, documents))
    if "nintendo_top_selling_titles" in chosen:
        outcome, parsed = _titles(catalog, fetch, root, moment)
        outcomes.append(outcome)
        documents.extend(parsed)
    if "igdb_game_metadata" in chosen:
        outcomes.append(igdb_outcome(moment, output_root=root))
    if "licensed_public_sales" in chosen:
        outcomes.append(licensed_outcome(root))

    if load_warehouse and documents:
        _load_warehouse(documents, outcomes)
    for outcome in outcomes:
        logger.info(
            "%s %s accepted=%s rejected=%s missing=%s %s",
            outcome.source_id,
            outcome.status,
            outcome.accepted,
            outcome.rejected,
            outcome.missing,
            outcome.message,
        )
    return outcomes


def genuine_official_count(outcomes: list[SourceOutcome]) -> int:
    return sum(
        outcome.accepted
        for outcome in outcomes
        if outcome.source_class == "official_ir" and outcome.status == "loaded"
    )


def _dedicated(catalog, fetch, root: Path, moment: datetime):
    source = catalog["nintendo_dedicated_unit_sales"]
    try:
        body, filename, method = _fetch_or_manual(
            source.url,
            fetch,
            root / "raw" / "manual" / source.source_id,
            ".html",
        )
    except FetchError as exc:
        return _unavailable(source.source_id, "official_ir", str(exc)), []
    saved = _save_raw(root, f"{source.source_id}.html", body)
    try:
        document = parse_dedicated_units(
            body.decode("utf-8", errors="replace"),
            source_url=source.url,
            retrieved_at=moment,
            raw_filename=saved.name,
        )
    except (HtmlParseError, NihError) as exc:
        return _failed(source.source_id, "official_ir", str(exc)), []
    dedupe_rows(document)
    _save_cleaned(root, document)
    outcome = _loaded(document, f"Retrieved by {method} from {filename}.")
    return outcome, [document]


def _titles(catalog, fetch, root: Path, moment: datetime):
    source = catalog["nintendo_top_selling_titles"]
    manual = root / "raw" / "manual" / source.source_id
    pages: list[tuple[str, str, bytes]] = []
    try:
        index_body = fetch(source.url)
    except FetchError as exc:
        pages = _manual_title_pages(manual, source.url)
        if not pages:
            return _unavailable(source.source_id, "official_ir", str(exc)), []
    else:
        _save_raw(root, f"{source.source_id}_index.html", index_body)
        html = index_body.decode("utf-8", errors="replace")
        pages.append(("switch2", source.url, index_body))
        for key, href in (("switch", "switch.html"), ("wiiu", "wiiu.html"), ("3ds", "3ds.html")):
            page_url = urljoin(source.url, href)
            try:
                pages.append((key, page_url, fetch(page_url)))
            except FetchError as exc:
                logger.warning("title page unavailable %s: %s", page_url, exc)
    documents: list[ParsedDocument] = []
    errors: list[str] = []
    for key, page_url, body in pages:
        saved = _save_raw(root, f"{source.source_id}_{key}.html", body)
        try:
            document = parse_title_page(
                body.decode("utf-8", errors="replace"),
                source_url=page_url,
                page_key=key,
                retrieved_at=moment,
                raw_filename=saved.name,
            )
        except (HtmlParseError, NihError) as exc:
            errors.append(f"{key}: {exc}")
            continue
        dedupe_rows(document)
        _save_cleaned(root, document)
        documents.append(document)
    if not documents:
        return _failed(source.source_id, "official_ir", "; ".join(errors) or "No title pages were parsed."), []
    accepted = sum(len(document.rows) for document in documents)
    rejected = sum(len(document.rejections) for document in documents)
    missing = sum(document.missing_cells for document in documents)
    message = f"Parsed {len(documents)} title pages."
    if errors:
        message = f"{message} Unavailable pages: {'; '.join(errors)}"
    return (
        SourceOutcome(
            source.source_id,
            "official_ir",
            "loaded",
            accepted,
            rejected,
            missing,
            message,
        ),
        documents,
    )


def _historical(chosen, catalog, fetch, root: Path, moment: datetime, documents: list[ParsedDocument]):
    index_source = catalog["nintendo_historical_region_sales"]
    wanted = {
        "sales": "nintendo_historical_region_sales" in chosen,
        "income": "nintendo_historical_income" in chosen,
    }
    discovered: list[dict[str, str]] = []
    index_error = ""
    try:
        index_body = fetch(index_source.url)
    except FetchError as exc:
        index_error = str(exc)
    else:
        _save_raw(root, "nintendo_historical_index.html", index_body)
        try:
            discovered = discover_historical_files(
                index_body.decode("utf-8", errors="replace"),
                index_source.url,
            )
        except WorkbookParseError as exc:
            index_error = str(exc)
    outcomes = []
    for kind, source_id in (("sales", "nintendo_historical_region_sales"), ("income", "nintendo_historical_income")):
        if not wanted[kind]:
            continue
        match = next((item for item in discovered if item["kind"] == kind), None)
        body = None
        source_url = ""
        filename = ""
        as_of = None
        method = "download"
        if match is not None:
            source_url = match["url"]
            filename = match["filename"]
            try:
                body = fetch(source_url)
            except FetchError as exc:
                body = _manual_bytes(root / "raw" / "manual" / source_id, Path(filename).suffix)
                method = "manual file"
                if body is None:
                    outcomes.append(_unavailable(source_id, "official_ir", str(exc)))
                    continue
            from datetime import date

            as_of = date.fromisoformat(match["as_of"])
        else:
            manual = _manual_file(root / "raw" / "manual" / source_id, ".xlsx" if kind == "sales" else ".xls")
            if manual is None:
                outcomes.append(
                    _unavailable(
                        source_id,
                        "official_ir",
                        index_error or "The historical index did not link this file.",
                    )
                )
                continue
            body = manual.read_bytes()
            filename = manual.name
            source_url = index_source.url
            as_of = as_of_from_filename(manual.name)
            method = "manual file"
        saved = _save_raw(root, filename, body)
        try:
            if kind == "sales":
                document = parse_sales_workbook(
                    saved,
                    source_url=source_url,
                    as_of=as_of,
                    retrieved_at=moment,
                    raw_filename=saved.name,
                )
            else:
                document = parse_income_workbook(
                    saved,
                    source_url=source_url,
                    as_of=as_of,
                    retrieved_at=moment,
                    raw_filename=saved.name,
                )
        except (WorkbookParseError, NihError) as exc:
            outcomes.append(_failed(source_id, "official_ir", str(exc)))
            continue
        _save_cleaned(root, document)
        documents.append(document)
        outcomes.append(_loaded(document, f"Retrieved by {method}: {filename}."))
    return outcomes


def _load_warehouse(documents: list[ParsedDocument], outcomes: list[SourceOutcome]) -> None:
    from warehouse.audit import database_reachable

    official = [document for document in documents if document.rows]
    if not official:
        return
    if not database_reachable():
        note = " PostgreSQL was not reachable, so the warehouse was not updated."
        for outcome in outcomes:
            if outcome.source_class == "official_ir" and outcome.status == "loaded":
                outcome.message += note
        return
    try:
        from ingestion.warehouse import load_documents

        written = load_documents(official)
    except Exception as exc:
        for outcome in outcomes:
            if outcome.source_class == "official_ir" and outcome.status == "loaded":
                outcome.warehouse_error = str(exc)
                outcome.message += f" Warehouse load failed: {exc}"
        return
    remaining = written
    for outcome in outcomes:
        if outcome.source_class == "official_ir" and outcome.status == "loaded":
            outcome.warehouse_rows = outcome.accepted
            remaining -= outcome.accepted
    logger.info("warehouse official rows written: %s", written)


def _fetch_or_manual(url: str, fetch: Fetcher, manual_dir: Path, suffix: str) -> tuple[bytes, str, str]:
    try:
        return fetch(url), url, "download"
    except FetchError:
        manual = _manual_file(manual_dir, suffix)
        if manual is None:
            raise
        return manual.read_bytes(), manual.name, "manual file"


def _manual_file(folder: Path, suffix: str) -> Path | None:
    if not folder.is_dir():
        return None
    files = sorted(folder.glob(f"*{suffix}"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _manual_bytes(folder: Path, suffix: str) -> bytes | None:
    manual = _manual_file(folder, suffix)
    if manual is None:
        return None
    return manual.read_bytes()


def _manual_title_pages(folder: Path, index_url: str) -> list[tuple[str, str, bytes]]:
    pages = []
    for key in ("switch2", "switch", "wiiu", "3ds"):
        path = folder / f"{key}.html"
        if not path.is_file():
            continue
        page_url = index_url if key == "switch2" else urljoin(index_url, f"{key}.html")
        pages.append((key, page_url, path.read_bytes()))
    return pages


def _save_raw(root: Path, filename: str, body: bytes) -> Path:
    destination = root / "raw" / "nintendo"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / filename
    path.write_bytes(body)
    return path


def _save_cleaned(root: Path, document: ParsedDocument) -> None:
    destination = root / "cleaned" / "nintendo"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{document.source_document_id}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLEANED_COLUMNS)
        writer.writeheader()
        for row in document.rows:
            writer.writerow(cleaned_record(document, row))
    rejected = destination / f"{document.source_document_id}_rejected.csv"
    with rejected.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_document_id",
                "reason",
                "detail",
                "period_label",
                "platform_name",
                "region_name",
                "printed_value",
            ],
        )
        writer.writeheader()
        for item in document.rejections:
            writer.writerow(
                {
                    "source_document_id": item.source_document_id,
                    "reason": item.reason,
                    "detail": item.detail,
                    "period_label": item.period_label,
                    "platform_name": item.platform_name,
                    "region_name": item.region_name,
                    "printed_value": item.printed_value,
                }
            )


def _loaded(document: ParsedDocument, prefix: str) -> SourceOutcome:
    return SourceOutcome(
        source_id=document.source_id,
        source_class="official_ir",
        status="loaded",
        accepted=len(document.rows),
        rejected=len(document.rejections),
        missing=document.missing_cells,
        message=f"{prefix} Accepted {len(document.rows)} rows.",
    )


def _unavailable(source_id: str, source_class: str, message: str) -> SourceOutcome:
    return SourceOutcome(
        source_id,
        source_class,
        "unavailable",
        0,
        0,
        0,
        f"Unavailable: {message} No substitute rows were written.",
    )


def _failed(source_id: str, source_class: str, message: str) -> SourceOutcome:
    return SourceOutcome(
        source_id,
        source_class,
        "failed",
        0,
        0,
        0,
        f"Failed: {message} No substitute rows were written.",
    )
