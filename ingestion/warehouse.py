"""Load parsed official documents into the local warehouse.

An unchanged file checksum leaves that document's rows in place. A new or
corrected document replaces only its own rows. Other documents, and the
synthetic weekly series, are left alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ingestion.records import ParsedDocument
from nih.db import connect
from nih.periods import ProductGrain


@dataclass(frozen=True)
class DocumentLoad:
    source_document_id: str
    action: str
    inserted: int
    updated: int
    unchanged: int
    removed: int


@dataclass(frozen=True)
class LoadSummary:
    documents: tuple[DocumentLoad, ...]

    @property
    def inserted(self) -> int:
        return sum(item.inserted for item in self.documents)

    @property
    def updated(self) -> int:
        return sum(item.updated for item in self.documents)

    @property
    def unchanged(self) -> int:
        return sum(item.unchanged for item in self.documents)

    @property
    def removed(self) -> int:
        return sum(item.removed for item in self.documents)


def classify_row_changes(
    existing: dict[tuple, Decimal | None],
    incoming: dict[tuple, Decimal | None],
) -> tuple[int, int, int, int]:
    """Return inserted, updated, unchanged, and removed row counts.

    The key is the fact grain. The value is the normalized measure.
    """

    inserted = updated = unchanged = removed = 0
    for key, value in incoming.items():
        if key not in existing:
            inserted += 1
        elif existing[key] == value:
            unchanged += 1
        else:
            updated += 1
    for key in existing:
        if key not in incoming:
            removed += 1
    return inserted, updated, unchanged, removed


def load_documents(documents: list[ParsedDocument]) -> LoadSummary:
    """Insert or skip official documents. Return one result per document."""

    loads: list[DocumentLoad] = []
    with connect() as connection:
        with connection.transaction():
            for document in documents:
                loads.append(_load_one(connection, document))
    return LoadSummary(tuple(loads))


def _load_one(connection, document: ParsedDocument) -> DocumentLoad:
    stored_hash, stored_rows = _stored_state(connection, document.source_document_id)
    if stored_hash == document.content_sha256 and stored_rows == len(document.rows) and stored_rows > 0:
        _audit(
            connection,
            document,
            stored_rows,
            "checksum unchanged; official rows were not rewritten.",
        )
        return DocumentLoad(
            document.source_document_id,
            "unchanged",
            0,
            0,
            stored_rows,
            0,
        )
    existing = _existing_values(connection, document.source_document_id)
    incoming = _incoming_values(document)
    inserted, updated, unchanged, removed = classify_row_changes(existing, incoming)
    action = "inserted" if not existing else "updated"
    _replace_document(connection, document)
    _audit(
        connection,
        document,
        len(document.rows),
        (
            f"{action} from {document.source_url}; "
            f"inserted={inserted} updated={updated} unchanged={unchanged} removed={removed}"
        ),
    )
    return DocumentLoad(
        document.source_document_id,
        action,
        inserted,
        updated,
        unchanged,
        removed,
    )


def _stored_state(connection, source_document_id: str) -> tuple[str | None, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select content_sha256
            from meta.source_document
            where source_document_id = %s
            """,
            (source_document_id,),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            select
                (select count(*) from raw_official.unit_sales_disclosure where source_document_id = %s)
                + (select count(*) from raw_official.financial_line where source_document_id = %s)
            """,
            (source_document_id, source_document_id),
        )
        count = int(cursor.fetchone()[0])
    return (None if row is None else row[0]), count


def _existing_values(connection, source_document_id: str) -> dict[tuple, Decimal | None]:
    values: dict[tuple, Decimal] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
                metric_code, platform_code, region_code, coalesce(game_code, ''),
                coalesce(fiscal_year_ending, 0), period_span, coalesce(fiscal_quarter, 0),
                is_forecast, value_units
            from raw_official.unit_sales_disclosure
            where source_document_id = %s
            """,
            (source_document_id,),
        )
        for row in cursor.fetchall():
            values[("unit", *row[:-1])] = None if row[-1] is None else Decimal(row[-1])
        cursor.execute(
            """
            select
                metric_code, region_code, coalesce(fiscal_year_ending, 0), period_span,
                coalesce(fiscal_quarter, 0), is_forecast, amount_yen
            from raw_official.financial_line
            where source_document_id = %s
            """,
            (source_document_id,),
        )
        for row in cursor.fetchall():
            values[("financial", *row[:-1])] = None if row[-1] is None else Decimal(row[-1])
    return values


def _incoming_values(document: ParsedDocument) -> dict[tuple, Decimal | None]:
    values: dict[tuple, Decimal] = {}
    for row in document.rows:
        measure = row.measure
        if measure.product_grain is ProductGrain.FINANCIAL_LINE:
            key = (
                "financial",
                measure.metric_code,
                measure.region_code,
                measure.fiscal_year_ending or 0,
                measure.period_span.value,
                measure.fiscal_quarter or 0,
                measure.is_forecast,
            )
        else:
            key = (
                "unit",
                measure.metric_code,
                measure.platform_code,
                measure.region_code,
                measure.game_code or "",
                measure.fiscal_year_ending or 0,
                measure.period_span.value,
                measure.fiscal_quarter or 0,
                measure.is_forecast,
            )
        values[key] = Decimal(measure.value)
    return values


def _audit(connection, document: ParsedDocument, row_count: int, note: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into meta.load_audit (action, row_count, note)
            values (%s, %s, %s)
            """,
            ("ingest_official", row_count, f"{document.source_document_id} {note}"),
        )


def _replace_document(connection, document: ParsedDocument) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "delete from raw_official.unit_sales_disclosure where source_document_id = %s",
            (document.source_document_id,),
        )
        cursor.execute(
            "delete from raw_official.financial_line where source_document_id = %s",
            (document.source_document_id,),
        )
        cursor.execute(
            """
            insert into meta.source_document (
                source_document_id, source_class, publisher_name, title, published_on,
                source_url, period_label_verbatim, content_sha256, retrieved_at
            ) values (%s, 'official_ir', %s, %s, %s, %s, %s, %s, %s)
            on conflict (source_document_id) do update set
                title = excluded.title,
                published_on = excluded.published_on,
                source_url = excluded.source_url,
                period_label_verbatim = excluded.period_label_verbatim,
                content_sha256 = excluded.content_sha256,
                retrieved_at = excluded.retrieved_at
            """,
            (
                document.source_document_id,
                document.publisher,
                document.title,
                document.published_on,
                document.source_url,
                document.period_label_verbatim,
                document.content_sha256,
                document.retrieved_at,
            ),
        )
        unit_rows = []
        financial_rows = []
        for row in document.rows:
            measure = row.measure
            if measure.product_grain is ProductGrain.FINANCIAL_LINE:
                financial_rows.append(
                    (
                        measure.source_document_id,
                        measure.metric_code,
                        measure.region_code,
                        measure.is_region_aggregate,
                        measure.fiscal_year_ending,
                        measure.period_span.value,
                        measure.fiscal_quarter,
                        measure.period_start,
                        measure.period_end,
                        measure.as_of_date,
                        row.printed_value,
                        row.scale_token,
                        measure.value,
                        measure.is_forecast,
                        measure.is_additive_flow,
                        row.definition_note,
                        row.retrieved_at,
                    )
                )
            else:
                unit_rows.append(
                    (
                        measure.source_document_id,
                        measure.metric_code,
                        measure.product_grain.value,
                        measure.platform_code,
                        measure.is_platform_aggregate,
                        measure.is_platform_component,
                        measure.parent_platform_code,
                        measure.game_code,
                        measure.region_code,
                        measure.is_region_aggregate,
                        measure.fiscal_year_ending,
                        measure.period_span.value,
                        measure.fiscal_quarter,
                        measure.period_start,
                        measure.period_end,
                        measure.as_of_date,
                        measure.value,
                        int(row.scale_token),
                        row.printed_value,
                        measure.is_forecast,
                        measure.is_additive_flow,
                        row.definition_note,
                        row.retrieved_at,
                    )
                )
        if unit_rows:
            cursor.executemany(
                """
                insert into raw_official.unit_sales_disclosure (
                    source_document_id, source_class, metric_code, product_grain,
                    platform_code, is_platform_aggregate, is_platform_component,
                    parent_platform_code, game_code, region_code, is_region_aggregate,
                    fiscal_year_ending, period_span, fiscal_quarter, period_start,
                    period_end, as_of_date, value_units, source_unit_scale,
                    source_value_as_printed, is_forecast, is_additive_flow,
                    sales_basis, definition_note, retrieved_at
                ) values (
                    %s, 'official_ir', %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    'sell_in', %s, %s
                )
                """,
                unit_rows,
            )
        if financial_rows:
            cursor.executemany(
                """
                insert into raw_official.financial_line (
                    source_document_id, source_class, metric_code, region_code,
                    is_region_aggregate, fiscal_year_ending, period_span, fiscal_quarter,
                    period_start, period_end, as_of_date, amount_as_printed, printed_scale,
                    amount_yen, is_forecast, is_additive_flow, definition_note, retrieved_at
                ) values (
                    %s, 'official_ir', %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                financial_rows,
            )
