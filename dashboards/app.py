"""Streamlit shell for the Nintendo Intelligence Hub foundation."""

from __future__ import annotations

from datetime import date

import pandas as pd


def main() -> None:
    import streamlit as st

    from dashboards.spans import build_span_figure
    from ingestion.registry import load_metric_catalog, load_source_catalog
    from nih import __version__
    from nih.config import describe_target, load_settings
    from nih.fiscal import fiscal_quarter, fiscal_year_ending

    st.set_page_config(page_title="Nintendo Intelligence Hub", layout="wide")
    st.title("Nintendo Intelligence Hub")
    st.caption(
        "Unofficial portfolio foundation. Not affiliated with Nintendo. "
        f"Version {__version__}. Official measure tables stay empty until a reviewed transcription."
    )

    settings = load_settings()
    today = date.today()
    current_fy = fiscal_year_ending(today)
    sources = load_source_catalog()
    metrics = load_metric_catalog()

    target_col, fiscal_col, counts_col = st.columns(3)
    target_col.metric("Warehouse", describe_target(settings).split("://", 1)[0])
    fiscal_col.metric("Today in the Nintendo fiscal calendar", f"FY3/{current_fy} Q{fiscal_quarter(today)}")
    counts = _warehouse_counts()
    if counts is None:
        counts_col.metric("Official measure rows", "Database offline")
    else:
        counts_col.metric(
            "Official measure rows",
            counts["official_unit_rows"] + counts["official_financial_rows"],
        )

    st.subheader("Period spans inside one fiscal year")
    st.write(
        "A nine-month disclosure runs from April 1 through December 31. "
        "The third fiscal quarter runs from October 1 through December 31. "
        "Life-to-date totals are omitted here because they do not start on April 1."
    )
    selected_year = st.selectbox(
        "Fiscal year ending March 31",
        options=[2024, 2025, 2026, 2027, 2028],
        index=[2024, 2025, 2026, 2027, 2028].index(current_fy if current_fy in range(2024, 2029) else 2026),
        format_func=lambda year: f"FY3/{year}",
    )
    st.plotly_chart(build_span_figure(int(selected_year)), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Source registry")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "source": source.source_id,
                        "class": source.source_class.value,
                        "title": source.title,
                        "grain": " ".join(source.grain.split()),
                        "url": source.url,
                    }
                    for source in sources
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.subheader("Metric catalog")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "metric": metric.metric_code,
                        "family": metric.measure_family,
                        "additive_flow": metric.additive_flow,
                        "unit": metric.native_unit,
                        "note": " ".join(metric.comparability_note.split()),
                    }
                    for metric in metrics
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Foundation status")
    st.dataframe(
        pd.DataFrame(
            [
                ("Ingestion", "Source registry and synthetic generator"),
                ("Warehouse", "PostgreSQL star schema and reference calendar"),
                ("Transformations", "Tested year-to-date derivation and dbt views"),
                ("Reported marts", "Views over official disclosures"),
                ("Simulated mart", "Isolated synthetic weekly series"),
                ("Monitoring", "Provenance, span, and aggregate-collision checks"),
                ("Forecasting", "Baseline trainer for simulated series"),
                ("Dashboard", "This shell"),
            ],
            columns=["Layer", "Foundation state"],
        ),
        use_container_width=True,
        hide_index=True,
    )
    if counts is not None:
        st.caption(
            f"Synthetic weekly rows in raw_simulated: {counts['simulated_rows']}. "
            "Those rows are a pipeline fixture and are not charted as performance."
        )
    st.caption("Grain rules: docs/DATA_GRAIN.md. Delivery phases: docs/IMPLEMENTATION_PLAN.md.")


def _warehouse_counts() -> dict[str, int] | None:
    from nih.config import load_settings
    from warehouse.audit import audit_database, database_reachable

    settings = load_settings()
    if not database_reachable(settings):
        return None
    try:
        return audit_database(settings)
    except Exception:
        return None


if __name__ == "__main__":
    main()
