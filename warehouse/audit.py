"""Read-only purity checks against the local warehouse."""

from __future__ import annotations

from nih.config import Settings, load_settings
from nih.db import connect
from nih.errors import ProvenanceError


PURITY_SQL = """
select 'official_unit_source' as check_name, count(*) as violations
from raw_official.unit_sales_disclosure
where source_class <> 'official_ir'
union all
select 'official_financial_source', count(*)
from raw_official.financial_line
where source_class <> 'official_ir'
   or entity_code <> 'nintendo_co_ltd_consolidated'
union all
select 'simulated_labels', count(*)
from raw_simulated.weekly_sell_through
where source_class <> 'simulated_operational'
   or series_name not like 'synthetic_%'
   or sku_code not like 'SYN_%'
   or region_code not like 'SIM_%'
   or char_length(disclaimer) < 40
"""


def database_reachable(settings: Settings | None = None) -> bool:
    settings = settings or load_settings()
    try:
        with connect(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
    except Exception:
        return False
    return True


def audit_database(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or load_settings()
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(PURITY_SQL)
            violations = {name: count for name, count in cursor.fetchall()}
            cursor.execute("select count(*) from raw_official.unit_sales_disclosure")
            official_units = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from raw_official.financial_line")
            official_financial = int(cursor.fetchone()[0])
            cursor.execute("select count(*) from raw_simulated.weekly_sell_through")
            simulated = int(cursor.fetchone()[0])
    failed = {name: count for name, count in violations.items() if count}
    if failed:
        raise ProvenanceError(f"Warehouse purity checks failed: {failed}")
    return {
        "official_unit_rows": official_units,
        "official_financial_rows": official_financial,
        "simulated_rows": simulated,
        "purity_violations": 0,
    }
