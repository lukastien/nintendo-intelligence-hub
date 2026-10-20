"""Parsed disclosure rows and the outcome of one source."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from nih.periods import DisclosureMeasure


@dataclass
class StagedRow:
    measure: DisclosureMeasure
    printed_value: Decimal
    scale_token: str
    period_label_verbatim: str
    platform_name_verbatim: str
    region_name_verbatim: str
    game_title: str | None
    sheet_name: str
    source_url: str
    content_sha256: str
    retrieved_at: datetime
    definition_note: str


@dataclass
class Rejection:
    source_document_id: str
    reason: str
    detail: str
    period_label: str = ""
    platform_name: str = ""
    region_name: str = ""
    printed_value: str = ""


@dataclass
class ParsedDocument:
    source_id: str
    source_document_id: str
    title: str
    source_url: str
    publisher: str
    published_on: date | None
    period_label_verbatim: str
    raw_filename: str
    content_sha256: str
    retrieved_at: datetime
    rows: list[StagedRow] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    missing_cells: int = 0


@dataclass
class SourceOutcome:
    source_id: str
    source_class: str
    status: str
    accepted: int
    rejected: int
    missing: int
    message: str
    warehouse_rows: int = 0
    warehouse_error: str = ""


CLEANED_COLUMNS = (
    "source_document_id",
    "source_url",
    "source_class",
    "publisher",
    "retrieved_at",
    "content_sha256",
    "metric_code",
    "measurement_type",
    "product_grain",
    "platform_code",
    "platform_name_verbatim",
    "is_platform_aggregate",
    "is_platform_component",
    "parent_platform_code",
    "region_code",
    "region_name_verbatim",
    "is_region_aggregate",
    "game_code",
    "game_title",
    "fiscal_year_ending",
    "period_span",
    "fiscal_quarter",
    "period_label_verbatim",
    "period_start",
    "period_end",
    "as_of_date",
    "printed_value",
    "scale_token",
    "normalized_value",
    "is_forecast",
    "is_additive_flow",
    "sales_basis",
    "definition_note",
    "sheet_name",
)


def measurement_type(row: StagedRow) -> str:
    measure = row.measure
    if measure.product_grain.value == "financial_line":
        return "consolidated_yen"
    if measure.period_span.value == "life_to_date":
        return "life_to_date_sell_in"
    if measure.period_span.value == "fiscal_year":
        return "fiscal_year_sell_in"
    if measure.period_span.value == "quarter":
        return "single_quarter_sell_in"
    return "cumulative_sell_in"


def cleaned_record(document: ParsedDocument, row: StagedRow) -> dict[str, str]:
    measure = row.measure
    return {
        "source_document_id": measure.source_document_id,
        "source_url": row.source_url,
        "source_class": measure.source_class.value,
        "publisher": document.publisher,
        "retrieved_at": row.retrieved_at.isoformat(),
        "content_sha256": row.content_sha256,
        "metric_code": measure.metric_code,
        "measurement_type": measurement_type(row),
        "product_grain": measure.product_grain.value,
        "platform_code": measure.platform_code,
        "platform_name_verbatim": row.platform_name_verbatim,
        "is_platform_aggregate": str(measure.is_platform_aggregate).lower(),
        "is_platform_component": str(measure.is_platform_component).lower(),
        "parent_platform_code": measure.parent_platform_code or "",
        "region_code": measure.region_code,
        "region_name_verbatim": row.region_name_verbatim,
        "is_region_aggregate": str(measure.is_region_aggregate).lower(),
        "game_code": measure.game_code or "",
        "game_title": row.game_title or "",
        "fiscal_year_ending": "" if measure.fiscal_year_ending is None else str(measure.fiscal_year_ending),
        "period_span": measure.period_span.value,
        "fiscal_quarter": "" if measure.fiscal_quarter is None else str(measure.fiscal_quarter),
        "period_label_verbatim": row.period_label_verbatim,
        "period_start": "" if measure.period_start is None else measure.period_start.isoformat(),
        "period_end": measure.period_end.isoformat(),
        "as_of_date": measure.as_of_date.isoformat(),
        "printed_value": format(row.printed_value, "f"),
        "scale_token": row.scale_token,
        "normalized_value": format(measure.value, "f"),
        "is_forecast": str(measure.is_forecast).lower(),
        "is_additive_flow": str(measure.is_additive_flow).lower(),
        "sales_basis": measure.sales_basis,
        "definition_note": row.definition_note,
        "sheet_name": row.sheet_name,
    }


def dedupe_rows(document: ParsedDocument) -> None:
    """Keep the first row for a disclosure grain and record the rest."""

    seen: dict[tuple, StagedRow] = {}
    kept: list[StagedRow] = []
    for row in document.rows:
        measure = row.measure
        key = (
            measure.metric_code,
            measure.platform_code,
            measure.region_code,
            measure.game_code or "",
            measure.fiscal_year_ending or 0,
            measure.period_span.value,
            measure.fiscal_quarter or 0,
            measure.is_forecast,
        )
        if key in seen:
            document.rejections.append(
                Rejection(
                    source_document_id=document.source_document_id,
                    reason="duplicate",
                    detail="A later cell repeated the same document grain. The first value was kept.",
                    period_label=row.period_label_verbatim,
                    platform_name=row.platform_name_verbatim,
                    region_name=row.region_name_verbatim,
                    printed_value=format(row.printed_value, "f"),
                )
            )
            continue
        seen[key] = row
        kept.append(row)
    document.rows = kept
