"""Load reference dimensions and the synthetic weekly sample."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from ingestion.registry import load_metric_catalog
from ingestion.simulate import SERIES_NAME, synthetic_weekly_sell_through
from nih.config import Settings, load_settings, project_root
from nih.db import connect
from nih.fiscal import build_date_dimension
from warehouse.apply import apply_sql_directory

DATE_START = date(1990, 4, 1)
DATE_END = date(2028, 3, 31)


def initialize_database(settings: Settings | None = None) -> dict:
    """Apply DDL, refresh reference data, and reload the synthetic sample.

    Official measure tables are left untouched by this bootstrap.
    """

    settings = settings or load_settings()
    ddl_dir = Path(__file__).resolve().parent / "ddl"
    with connect(settings) as connection:
        with connection.transaction():
            applied = apply_sql_directory(connection, ddl_dir)
            platforms = _upsert_platforms(connection)
            regions = _upsert_regions(connection)
            metrics = _upsert_metrics(connection)
            dates = _upsert_dates(connection)
            simulated = _reload_simulated(connection)
            official_units = _count(connection, "raw_official.unit_sales_disclosure")
            official_financial = _count(connection, "raw_official.financial_line")
            note = (
                "Reference dimensions refreshed. Synthetic weekly rows reloaded into "
                "raw_simulated. Official measure tables were not loaded."
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into meta.load_audit (action, row_count, note)
                    values (%s, %s, %s)
                    """,
                    ("init_db", simulated, note),
                )
            summary = {
                "ddl_scripts": applied,
                "platforms": platforms,
                "regions": regions,
                "metrics": metrics,
                "dates": dates,
                "simulated_rows": simulated,
                "official_unit_rows": official_units,
                "official_financial_rows": official_financial,
            }
    return summary


def _seed_path(name: str) -> Path:
    return project_root() / "warehouse" / "seeds" / name


def _read_seed(name: str) -> list[dict[str, str]]:
    with _seed_path(name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _blank(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _upsert_platforms(connection) -> int:
    rows = _read_seed("dim_platform.csv")
    sql = """
        insert into ref.dim_platform (
            platform_code, platform_name, family_code, is_aggregate, is_component,
            parent_platform_code, hardware_form, reference_note
        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (platform_code) do update set
            platform_name = excluded.platform_name,
            family_code = excluded.family_code,
            is_aggregate = excluded.is_aggregate,
            is_component = excluded.is_component,
            parent_platform_code = excluded.parent_platform_code,
            hardware_form = excluded.hardware_form,
            reference_note = excluded.reference_note
    """
    payload = [
        (
            row["platform_code"],
            row["platform_name"],
            row["family_code"],
            _bool(row["is_aggregate"]),
            _bool(row["is_component"]),
            _blank(row["parent_platform_code"]),
            row["hardware_form"],
            row["reference_note"],
        )
        for row in rows
    ]
    with connection.cursor() as cursor:
        cursor.executemany(sql, payload)
    return len(payload)


def _upsert_regions(connection) -> int:
    rows = _read_seed("dim_region.csv")
    sql = """
        insert into ref.dim_region (
            region_code, region_name, is_aggregate, aggregate_note, sort_order
        ) values (%s, %s, %s, %s, %s)
        on conflict (region_code) do update set
            region_name = excluded.region_name,
            is_aggregate = excluded.is_aggregate,
            aggregate_note = excluded.aggregate_note,
            sort_order = excluded.sort_order
    """
    payload = [
        (
            row["region_code"],
            row["region_name"],
            _bool(row["is_aggregate"]),
            row["aggregate_note"],
            int(row["sort_order"]),
        )
        for row in rows
    ]
    with connection.cursor() as cursor:
        cursor.executemany(sql, payload)
    return len(payload)


def _upsert_metrics(connection) -> int:
    records = load_metric_catalog()
    sql = """
        insert into ref.dim_metric (
            metric_code, metric_name, measure_family, additive_flow, native_unit,
            sales_basis, statement_scope, comparability_note
        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (metric_code) do update set
            metric_name = excluded.metric_name,
            measure_family = excluded.measure_family,
            additive_flow = excluded.additive_flow,
            native_unit = excluded.native_unit,
            sales_basis = excluded.sales_basis,
            statement_scope = excluded.statement_scope,
            comparability_note = excluded.comparability_note
    """
    payload = [
        (
            record.metric_code,
            record.metric_name,
            record.measure_family,
            record.additive_flow,
            record.native_unit,
            record.sales_basis,
            record.statement_scope,
            " ".join(record.comparability_note.split()),
        )
        for record in records
    ]
    with connection.cursor() as cursor:
        cursor.executemany(sql, payload)
    return len(payload)


def _upsert_dates(connection) -> int:
    rows = build_date_dimension(DATE_START, DATE_END)
    sql = """
        insert into ref.dim_date (
            date_key, calendar_date, calendar_year, calendar_month, calendar_quarter,
            iso_year, iso_week, nintendo_fiscal_year_ending, fiscal_label, fiscal_quarter,
            fiscal_quarter_start, fiscal_quarter_end, is_fiscal_quarter_end,
            fiscal_year_start, fiscal_year_end
        ) values (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        on conflict (date_key) do update set
            calendar_date = excluded.calendar_date,
            calendar_year = excluded.calendar_year,
            calendar_month = excluded.calendar_month,
            calendar_quarter = excluded.calendar_quarter,
            iso_year = excluded.iso_year,
            iso_week = excluded.iso_week,
            nintendo_fiscal_year_ending = excluded.nintendo_fiscal_year_ending,
            fiscal_label = excluded.fiscal_label,
            fiscal_quarter = excluded.fiscal_quarter,
            fiscal_quarter_start = excluded.fiscal_quarter_start,
            fiscal_quarter_end = excluded.fiscal_quarter_end,
            is_fiscal_quarter_end = excluded.is_fiscal_quarter_end,
            fiscal_year_start = excluded.fiscal_year_start,
            fiscal_year_end = excluded.fiscal_year_end
    """
    payload = [
        (
            row["date_key"],
            row["calendar_date"],
            row["calendar_year"],
            row["calendar_month"],
            row["calendar_quarter"],
            row["iso_year"],
            row["iso_week"],
            row["nintendo_fiscal_year_ending"],
            row["fiscal_label"],
            row["fiscal_quarter"],
            row["fiscal_quarter_start"],
            row["fiscal_quarter_end"],
            row["is_fiscal_quarter_end"],
            row["fiscal_year_start"],
            row["fiscal_year_end"],
        )
        for row in rows
    ]
    with connection.cursor() as cursor:
        cursor.executemany(sql, payload)
    return len(payload)


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    return value


def _reload_simulated(connection) -> int:
    frame = synthetic_weekly_sell_through()
    payload = [
        (
            row.source_class,
            row.series_name,
            int(row.iso_year),
            int(row.iso_week),
            _as_date(row.week_start),
            row.sku_code,
            row.region_code,
            row.channel_code,
            int(row.units),
            row.disclaimer,
        )
        for row in frame.itertuples(index=False)
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            "delete from raw_simulated.weekly_sell_through where series_name = %s",
            (SERIES_NAME,),
        )
        cursor.executemany(
            """
            insert into raw_simulated.weekly_sell_through (
                source_class, series_name, iso_year, iso_week, week_start,
                sku_code, region_code, channel_code, units, disclaimer
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            payload,
        )
    return len(payload)


def _count(connection, table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from {table}")
        return int(cursor.fetchone()[0])
