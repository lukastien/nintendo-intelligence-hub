"""Parameterized PostgreSQL queries for the dashboard.

All official figures come from the dbt marts in PostgreSQL. Nothing in
this module contains a sales figure. Credentials come from nih.config
and are never returned to the UI.
"""

from __future__ import annotations

import pandas as pd

from nih.config import Settings, load_settings
from nih.db import connect
from nih.errors import NihError


class DashboardDataError(NihError):
    """Raised when the warehouse cannot supply a dashboard query."""


_NUMERIC_COLUMNS = {
    "value_units",
    "hardware_units",
    "software_units",
    "software_units_per_hardware_unit",
    "disclosed_global_units",
    "regional_parts_sum",
    "global_minus_parts",
    "net_sales_yen",
    "operating_profit_yen",
    "ordinary_profit_yen",
    "profit_attributable_to_owners_yen",
    "operating_margin_calculated",
    "ordinary_margin_calculated",
    "profit_margin_calculated",
    "duration_seconds",
}


def database_available(settings: Settings | None = None) -> bool:
    try:
        with connect(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
    except Exception:
        return False
    return True


def annual_performance(
    *,
    platforms: list[str] | None = None,
    regions: list[str] | None = None,
    metrics: list[str] | None = None,
    fiscal_years: list[int] | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    where, params = _filters(
        platforms=platforms,
        regions=regions,
        metrics=metrics,
        fiscal_years=fiscal_years,
    )
    sql = f"""
        select *
        from mart_reported.mart_annual_platform_performance
        {where}
        order by fiscal_year_ending, platform_code, metric_code, region_code
    """
    return _query(sql, params, settings)


def hardware_software_trends(
    *,
    platforms: list[str] | None = None,
    regions: list[str] | None = None,
    fiscal_years: list[int] | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    where, params = _filters(platforms=platforms, regions=regions, fiscal_years=fiscal_years)
    sql = f"""
        select *
        from mart_reported.mart_hardware_software_trends
        {where}
        order by fiscal_year_ending, platform_code, region_code
    """
    return _query(sql, params, settings)


def lifetime_platform_sales(
    *,
    platforms: list[str] | None = None,
    regions: list[str] | None = None,
    metrics: list[str] | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    where, params = _filters(platforms=platforms, regions=regions, metrics=metrics)
    sql = f"""
        select *
        from mart_reported.mart_lifetime_platform_sales
        {where}
        order by platform_code, metric_code, region_code, as_of_date
    """
    return _query(sql, params, settings)


def regional_performance(
    *,
    platforms: list[str] | None = None,
    regions: list[str] | None = None,
    metrics: list[str] | None = None,
    fiscal_years: list[int] | None = None,
    region_layouts: list[str] | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    where, params = _filters(
        platforms=platforms,
        regions=regions,
        metrics=metrics,
        fiscal_years=fiscal_years,
        region_layouts=region_layouts,
    )
    sql = f"""
        select *
        from mart_reported.mart_regional_performance
        {where}
        order by fiscal_year_ending, platform_code, metric_code, region_code
    """
    return _query(sql, params, settings)


def financial_performance(*, settings: Settings | None = None) -> pd.DataFrame:
    return _query(
        """
        select *
        from mart_reported.mart_financial_performance
        order by fiscal_year_ending
        """,
        (),
        settings,
    )


def pipeline_runs(limit: int = 20, *, settings: Settings | None = None) -> pd.DataFrame:
    return _query(
        """
        select
            pipeline_run_id, started_at, finished_at, status, documents_processed,
            records_extracted, records_inserted, records_updated, records_unchanged,
            records_rejected, dbt_status, validation_failures, error_message,
            duration_seconds, detail
        from meta.pipeline_runs
        order by started_at desc
        limit %s
        """,
        (int(limit),),
        settings,
    )


def warehouse_counts(*, settings: Settings | None = None) -> dict[str, int]:
    frame = _query(
        """
        select
            (select count(*) from raw_official.unit_sales_disclosure) as official_unit_rows,
            (select count(*) from raw_official.financial_line) as official_financial_rows,
            (select count(*) from raw_simulated.weekly_sell_through) as simulated_rows,
            (select count(*) from mart_simulated.weekly_sell_through) as simulated_mart_rows
        """,
        (),
        settings,
    )
    if frame.empty:
        raise DashboardDataError("Warehouse counts returned no row.")
    row = frame.iloc[0]
    return {name: int(row[name]) for name in frame.columns}


def mart_counts(*, settings: Settings | None = None) -> dict[str, int]:
    names = [
        "mart_annual_platform_performance",
        "mart_hardware_software_trends",
        "mart_financial_performance",
        "mart_lifetime_platform_sales",
        "mart_regional_performance",
        "unit_sales_incremental_quarter",
        "financial_flow_incremental_quarter",
    ]
    counts: dict[str, int] = {}
    for name in names:
        frame = _query(f"select count(*) as row_count from mart_reported.{name}", (), settings)
        counts[name] = int(frame.iloc[0]["row_count"])
    frame = _query("select count(*) as row_count from mart_simulated.weekly_sell_through", (), settings)
    counts["weekly_sell_through"] = int(frame.iloc[0]["row_count"])
    return counts


def document_as_ofs(*, settings: Settings | None = None) -> list[tuple[str, object]]:
    frame = _query(
        """
        select source_document_id, max(as_of_date) as as_of_date
        from (
            select source_document_id, as_of_date from raw_official.unit_sales_disclosure
            union all
            select source_document_id, as_of_date from raw_official.financial_line
        ) as documents
        group by source_document_id
        order by source_document_id
        """,
        (),
        settings,
    )
    return [(str(row.source_document_id), row.as_of_date) for row in frame.itertuples()]


def latest_refresh(*, settings: Settings | None = None) -> object | None:
    """Most recent successful load or pipeline finish recorded in PostgreSQL."""
    frame = _query(
        """
        select max(finished_at) as refreshed_at
        from meta.pipeline_runs
        where status = 'succeeded'
        """,
        (),
        settings,
    )
    if frame.empty:
        return None
    value = frame.iloc[0]["refreshed_at"]
    return None if value is None or pd.isna(value) else value


def _filters(*, platforms=None, regions=None, metrics=None, fiscal_years=None, region_layouts=None) -> tuple[str, tuple]:
    clauses: list[str] = []
    params: list[object] = []
    for column, values in (
        ("platform_code", platforms),
        ("region_code", regions),
        ("metric_code", metrics),
        ("region_layout", region_layouts),
    ):
        if values:
            clauses.append(f"{column} = any(%s)")
            params.append(list(values))
    if fiscal_years:
        clauses.append("fiscal_year_ending = any(%s)")
        params.append([int(year) for year in fiscal_years])
    if not clauses:
        return "", ()
    return "where " + " and ".join(clauses), tuple(params)


def _query(sql: str, params: tuple, settings: Settings | None) -> pd.DataFrame:
    settings = settings or load_settings()
    try:
        with connect(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                columns = [column.name for column in cursor.description]
                rows = cursor.fetchall()
    except Exception as exc:
        raise DashboardDataError(f"PostgreSQL query failed: {exc}") from exc
    frame = pd.DataFrame(rows, columns=columns)
    for column in frame.columns:
        if column in _NUMERIC_COLUMNS or column.endswith("_yen") or column.endswith("_units"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame
