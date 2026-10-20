"""Load parsed official documents into the local warehouse.

Re-running a document replaces that document's rows. Other documents, and the
synthetic weekly series, are left alone.
"""

from __future__ import annotations

from ingestion.records import ParsedDocument
from nih.db import connect
from nih.periods import ProductGrain


def load_documents(documents: list[ParsedDocument]) -> int:
    """Insert official rows. Return the number of fact rows written."""

    written = 0
    with connect() as connection:
        with connection.transaction():
            for document in documents:
                _replace_document(connection, document)
                written += len(document.rows)
    return written


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
        cursor.execute(
            """
            insert into meta.load_audit (action, row_count, note)
            values (%s, %s, %s)
            """,
            (
                "ingest_official",
                len(document.rows),
                f"{document.source_document_id} replaced from {document.source_url}",
            ),
        )
