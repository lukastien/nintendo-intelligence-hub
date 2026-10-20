"""Nintendo Intelligence Hub — interactive BI dashboard.

Run with: streamlit run dashboards/app.py

Every official figure is read from the PostgreSQL dbt marts at run time.
The synthetic weekly series is counted on the Pipeline Health page only;
it is never charted as Nintendo performance.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from dashboards import calculations as calc
from dashboards import charts, components, queries
from dashboards.definitions import UNAVAILABLE_METRICS
from dashboards.formatting import (
    fiscal_label,
    format_count,
    format_percent,
    format_ratio,
    format_units,
    format_yen,
)

st.set_page_config(
    page_title="Nintendo Intelligence Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------- queries
@st.cache_data(ttl=300, show_spinner=False)
def _annual(platforms: tuple[str, ...] = (), regions: tuple[str, ...] = (), metrics: tuple[str, ...] = ()):
    return queries.annual_performance(
        platforms=list(platforms) or None,
        regions=list(regions) or None,
        metrics=list(metrics) or None,
    )


@st.cache_data(ttl=300, show_spinner=False)
def _trends(platforms: tuple[str, ...] = (), regions: tuple[str, ...] = ()): 
    return queries.hardware_software_trends(platforms=list(platforms) or None, regions=list(regions) or None)


@st.cache_data(ttl=300, show_spinner=False)
def _regional(platforms: tuple[str, ...] = (), layouts: tuple[str, ...] = ()): 
    return queries.regional_performance(platforms=list(platforms) or None, region_layouts=list(layouts) or None)


@st.cache_data(ttl=300, show_spinner=False)
def _lifetime(platforms: tuple[str, ...] = ()): 
    return queries.lifetime_platform_sales(platforms=list(platforms) or None)


@st.cache_data(ttl=300, show_spinner=False)
def _financial():
    return queries.financial_performance()


@st.cache_data(ttl=120, show_spinner=False)
def _pipeline(limit: int = 20):
    return queries.pipeline_runs(limit)


@st.cache_data(ttl=120, show_spinner=False)
def _counts():
    return queries.warehouse_counts()


@st.cache_data(ttl=120, show_spinner=False)
def _refresh():
    return queries.latest_refresh()


@st.cache_data(ttl=120, show_spinner=False)
def _documents():
    return queries.document_as_ofs()


def _platform_labels(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    pairs = frame[["platform_code", "platform_name"]].drop_duplicates().sort_values("platform_name")
    return {str(row.platform_code): str(row.platform_name) for row in pairs.itertuples()}


def _year_range(frame: pd.DataFrame, key: str) -> tuple[int, int] | None:
    years = sorted({int(y) for y in frame.get("fiscal_year_ending", pd.Series(dtype=float)).dropna().tolist()}) if not frame.empty else []
    if not years:
        st.info("No fiscal years are available for this selection.")
        return None
    low, high = int(years[0]), int(years[-1])
    if low == high:
        st.caption(f"Fiscal year: {fiscal_label(low)} (only year reported for this selection)")
        return low, high
    selected = st.slider(key, min_value=low, max_value=high, value=(low, high), format="FY3/%d")
    return int(selected[0]), int(selected[1])


def _chart_block(heading: str | None, figure, caption: str | None = None) -> None:
    """Render a descriptive Streamlit heading, then a title-less figure.

    Keeping the title in Streamlit means a long description wraps in the
    page instead of colliding with the Plotly legend inside the chart.
    """
    if heading:
        st.subheader(heading)
    if caption:
        st.caption(caption)
    st.plotly_chart(
        figure,
        use_container_width=True,
        config={"responsive": True, "displaylogo": False},
    )


def _definitions_expander(codes: list[str]) -> None:
    from dashboards.definitions import METRIC_DEFINITIONS

    with st.expander("Metric definitions and reporting basis"):
        for code in codes:
            item = METRIC_DEFINITIONS.get(code)
            if item:
                st.markdown(f"**{item['display_name']}** (`{code}`, {item['unit']}) — {item['definition']}")
                st.caption(item["caution"])


# ---------------------------------------------------------------- page 1
def executive_overview() -> None:
    components.header(
        st,
        "Executive overview",
        "Nintendo Intelligence Hub",
        "Annual reported performance from public Nintendo IR disclosures. Annual flows only — no quarterly series is derived.",
    )
    annual = _annual()
    financial = _financial()
    if annual.empty:
        st.warning("The annual platform mart returned no rows. Run `python -m nih pipeline run`, then reload.")
        return
    years = sorted({int(y) for y in annual["fiscal_year_ending"].dropna().unique()})
    selected = st.selectbox("Fiscal year", years, index=len(years) - 1, format_func=fiscal_label)

    hardware_total = calc.cross_platform_total(annual, selected, "hw_units_sell_in")
    software_total = calc.cross_platform_total(annual, selected, "sw_units_sell_in")
    hardware_yoy = calc.comparable_yoy(annual, selected, "hw_units_sell_in")
    software_yoy = calc.comparable_yoy(annual, selected, "sw_units_sell_in")
    fin = calc.financial_for_year(financial, selected)

    cards = st.columns(4)
    with cards[0]:
        note = "Comparable YoY unavailable" if hardware_yoy is None else f"YoY {format_percent(hardware_yoy['growth'])} on the same platform set"
        components.kpi_card(st, f"Worldwide hardware · {fiscal_label(selected)}", format_units(hardware_total), note)
    with cards[1]:
        note = "Comparable YoY unavailable" if software_yoy is None else f"YoY {format_percent(software_yoy['growth'])} on the same platform set"
        components.kpi_card(st, f"Worldwide software · {fiscal_label(selected)}", format_units(software_total), note)
    with cards[2]:
        components.kpi_card(
            st,
            "Consolidated net sales",
            format_yen(fin["net_sales_yen"] if fin else None),
            "Nintendo Co., Ltd. group, worldwide (JPY). Not Nintendo of America revenue.",
        )
    with cards[3]:
        margin = fin["operating_margin"] if fin else None
        components.kpi_card(
            st,
            "Operating profit · margin",
            f"{format_yen(fin['operating_profit_yen'] if fin else None)} · {format_percent(margin, 1).replace('+', '')}" if fin and margin is not None else format_yen(fin["operating_profit_yen"] if fin else None),
            "Margin is calculated from the two consolidated annual flows.",
        )
    if hardware_yoy is None or software_yoy is None:
        st.caption(
            "A comparable year-over-year total is shown only when the same non-component platform scopes "
            "reported in both years. A launch or a retired platform makes the summed total non-comparable, so the growth is left blank rather than implied."
        )

    worldwide = calc.filter_annual(annual, regions="GLOBAL")
    worldwide = worldwide[worldwide["include_in_cross_platform_total"] == True]  # noqa: E712
    trend = (
        worldwide.groupby(["fiscal_year_ending", "metric_code"], as_index=False)["value_units"].sum()
        if not worldwide.empty
        else worldwide
    )
    trend = trend.assign(observation_type="annual_flow", period_span="fiscal_year")
    left, right = st.columns(2)
    with left:
        _chart_block(
            "Annual hardware & software sell-in",
            charts.annual_metric_chart(trend, title="Annual hardware and software sell-in"),
            caption="Worldwide · non-component platform scopes · fiscal-year flows",
        )
    with right:
        _chart_block(
            "Consolidated financial performance",
            charts.financial_chart(financial, title="Consolidated financial performance"),
            caption="Nintendo Co., Ltd. group · JPY · fiscal-year flows",
        )

    comparison = calc.filter_annual(annual, fiscal_years=selected, regions="GLOBAL", metrics="hw_units_sell_in")
    comparison = comparison[comparison["include_in_cross_platform_total"] == True]  # noqa: E712
    _chart_block(
        f"Hardware sell-in by platform — {fiscal_label(selected)}",
        charts.platform_comparison_chart(comparison, selected, title="Hardware sell-in by platform"),
        caption="Worldwide · family totals counted once · component models excluded",
    )
    st.caption("Family totals appear once. Component models (for example Switch Lite inside the Switch family) are excluded from this comparison and from the totals above.")

    st.subheader("Executive observations")
    components.insight_list(st, calc.executive_insights(annual, financial, selected))
    st.caption("Observations are descriptive rankings and changes computed from the rows above. They do not explain why a result occurred.")
    _definitions_expander(["hw_units_sell_in", "sw_units_sell_in", "net_sales_jpy", "operating_profit_jpy", "operating_margin_calculated"])


# ---------------------------------------------------------------- page 2
def hardware_software() -> None:
    components.header(
        st,
        "Hardware & software analytics",
        "Platform performance",
        "Annual fiscal-year flows are charted separately from life-to-date snapshots.",
    )
    trends = _trends()
    lifetime = _lifetime()
    if trends.empty:
        st.warning("The hardware/software trend mart returned no rows.")
        return
    labels = _platform_labels(trends)
    platform = st.selectbox("Platform scope", list(labels), format_func=lambda code: labels[code])
    regions = sorted({str(r) for r in trends["region_code"].dropna().unique()})
    region = st.selectbox("Region", regions, index=regions.index("GLOBAL") if "GLOBAL" in regions else 0)
    frame = calc.filter_annual(trends, platforms=platform, regions=region) if "observation_type" in trends else trends[(trends["platform_code"] == platform) & (trends["region_code"] == region)]
    year_range = _year_range(frame, "Platform fiscal years")
    if year_range is None:
        return
    frame = frame[(frame["fiscal_year_ending"] >= year_range[0]) & (frame["fiscal_year_ending"] <= year_range[1])].sort_values("fiscal_year_ending")
    name = labels.get(platform, platform)

    latest = frame.iloc[-1] if not frame.empty else None
    cards = st.columns(3)
    with cards[0]:
        components.kpi_card(st, f"Hardware · {fiscal_label(latest['fiscal_year_ending']) if latest is not None else ''}", format_units(latest["hardware_units"]) if latest is not None else "Not reported", name)
    with cards[1]:
        components.kpi_card(st, "Software", format_units(latest["software_units"]) if latest is not None else "Not reported", "Annual platform software total")
    with cards[2]:
        ratio = calc.software_hardware_ratio(latest["hardware_units"], latest["software_units"]) if latest is not None else None
        components.kpi_card(st, "Software per hardware unit", format_ratio(ratio), "Blank when hardware is zero or a metric is missing")

    _chart_block(
        f"{name} — annual hardware & software",
        charts.hardware_software_chart(frame, platform_name=name),
        caption=f"{region} · fiscal-year flows",
    )
    _chart_block(
        f"{name} — software per hardware unit",
        charts.ratio_chart(frame, platform_name=name),
        caption="Annual software ÷ annual hardware. Blank where hardware is zero or missing.",
    )
    st.dataframe(
        frame[["fiscal_year_ending", "hardware_units", "software_units", "software_units_per_hardware_unit", "both_metrics_present"]],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Historical platform comparison")
    annual = _annual()
    years = sorted({int(y) for y in annual["fiscal_year_ending"].dropna().unique()}) if not annual.empty else []
    if years:
        compare_year = st.selectbox("Comparison fiscal year", years, index=len(years) - 1, format_func=fiscal_label, key="compare_year")
        comparison = calc.filter_annual(annual, fiscal_years=compare_year, regions="GLOBAL", metrics="hw_units_sell_in")
        comparison = comparison[comparison["include_in_cross_platform_total"] == True]  # noqa: E712
        _chart_block(
            f"Hardware sell-in by platform — {fiscal_label(compare_year)}",
            charts.platform_comparison_chart(comparison, compare_year, title="Hardware sell-in by platform"),
            caption="Worldwide · non-component platform scopes",
        )

    st.subheader("Life-to-date snapshots")
    st.caption("Point-in-time cumulative totals. Each as-of date is shown on its own; snapshots are never summed and are not annual sales.")
    life = calc.filter_lifetime(lifetime, platforms=platform, regions="GLOBAL")
    if life.empty:
        st.info("No life-to-date snapshot is reported for this platform scope worldwide.")
    else:
        _chart_block(None, charts.lifetime_chart(life, platform_name=name))
        st.dataframe(
            life[["as_of_date", "metric_code", "value_units", "is_latest_as_of", "source_document_id"]],
            use_container_width=True,
            hide_index=True,
        )
    _definitions_expander(["hw_units_sell_in", "sw_units_sell_in", "software_units_per_hardware_unit"])


# ---------------------------------------------------------------- page 3
def regional_performance() -> None:
    components.header(
        st,
        "Regional performance",
        "Reported regions, preserved as printed",
        "Europe-split and Europe-inside-Other are different reporting definitions and are never combined.",
    )
    regional = _regional()
    if regional.empty:
        st.warning("The regional mart returned no rows.")
        return
    layouts = {
        "europe_split": "Europe split out (Japan · Americas · Europe · Other)",
        "europe_inside_other": "Europe inside Other (Japan · Americas · Other incl. Europe)",
        "incomplete_regional_breakdown": "Incomplete breakdown (overseas split not printed)",
    }
    available_layouts = [code for code in layouts if code in set(regional["region_layout"].dropna())]
    layout = st.selectbox("Region definition", available_layouts, format_func=lambda code: layouts[code])
    scoped = regional[regional["region_layout"] == layout]
    labels = _platform_labels(scoped)
    if not labels:
        st.info("No platform reported under this region definition.")
        return
    platform = st.selectbox("Platform scope", list(labels), format_func=lambda code: labels[code])
    metric = st.selectbox("Metric", ["hw_units_sell_in", "sw_units_sell_in"], format_func=lambda code: "Hardware units" if code.startswith("hw") else "Software units")
    scoped = scoped[(scoped["platform_code"] == platform) & (scoped["metric_code"] == metric)]
    regions = sorted({str(r) for r in scoped["region_code"].dropna().unique()})
    selected_regions = st.multiselect("Regions", regions, default=regions)
    scoped = scoped[scoped["region_code"].isin(selected_regions)]
    year_range = _year_range(scoped, "Regional fiscal years")
    if year_range is None:
        return
    scoped = scoped[(scoped["fiscal_year_ending"] >= year_range[0]) & (scoped["fiscal_year_ending"] <= year_range[1])]
    name = labels.get(platform, platform)

    _chart_block(
        f"{name} — regional annual sell-in",
        charts.regional_chart(scoped, title="Regional annual sell-in"),
        caption=layouts[layout],
    )
    enriched = calc.add_regional_share(scoped)
    display = enriched.copy()
    display["share_label"] = display["regional_share"].map(lambda v: "Unavailable" if pd.isna(v) else format_percent(float(v), 1).replace("+", ""))
    st.dataframe(
        display[["fiscal_year_ending", "region_code", "value_units", "disclosed_global_units", "share_label", "reconciliation_status"]],
        use_container_width=True,
        hide_index=True,
    )
    if layout == "incomplete_regional_breakdown":
        st.warning("This selection has no complete overseas breakdown in the source sheet. Regional share of worldwide is unavailable and the parts must not be treated as a worldwide total.")
    else:
        statuses = sorted({str(s) for s in scoped["reconciliation_status"].dropna().unique()})
        st.caption(f"Reconciliation of the parts to the disclosed worldwide total for this selection: {', '.join(statuses)}. The disclosed worldwide total is kept as printed; it is not replaced by the sum of the parts.")
    st.caption("Worldwide (GLOBAL) is not a row in this mart. It is shown only as disclosed_global_units for reference and is never added to the regional rows.")
    _definitions_expander(["hw_units_sell_in", "sw_units_sell_in", "regional_share"])


# ---------------------------------------------------------------- page 4
def financial_intelligence() -> None:
    components.header(
        st,
        "Financial intelligence",
        "Consolidated Nintendo Co., Ltd. results",
        "Worldwide group financials in yen. These are not Nintendo of America standalone results and have no platform split.",
    )
    financial = _financial()
    if financial.empty:
        st.warning("The financial mart returned no rows.")
        return
    year_range = _year_range(financial, "Financial fiscal years")
    if year_range is None:
        return
    frame = financial[(financial["fiscal_year_ending"] >= year_range[0]) & (financial["fiscal_year_ending"] <= year_range[1])].sort_values("fiscal_year_ending")
    selected_year = int(frame["fiscal_year_ending"].max())
    selected = st.selectbox("KPI fiscal year", [int(y) for y in frame["fiscal_year_ending"]], index=len(frame) - 1, format_func=fiscal_label)
    fin = calc.financial_for_year(financial, selected)

    cards = st.columns(4)
    items = [
        ("Net sales", format_yen(fin["net_sales_yen"] if fin else None), "Consolidated (JPY)"),
        ("Operating profit", format_yen(fin["operating_profit_yen"] if fin else None), "Consolidated (JPY)"),
        ("Ordinary profit", format_yen(fin["ordinary_profit_yen"] if fin else None), "Consolidated (JPY)"),
        ("Profit attributable to owners", format_yen(fin["profit_attributable_to_owners_yen"] if fin else None), "Consolidated (JPY)"),
    ]
    for column, (label, value, note) in zip(cards, items, strict=True):
        with column:
            components.kpi_card(st, f"{label} · {fiscal_label(selected)}", value, note)
    if fin:
        margin_cards = st.columns(2)
        with margin_cards[0]:
            components.kpi_card(st, "Operating margin (calculated)", format_percent(fin["operating_margin"], 1).replace("+", ""), "Operating profit ÷ net sales")
        with margin_cards[1]:
            components.kpi_card(st, "Net profit margin (calculated)", format_percent(fin["profit_margin"], 1).replace("+", ""), "Profit attributable to owners ÷ net sales")

    _chart_block(
        "Consolidated amounts",
        charts.financial_chart(frame),
        caption="Nintendo Co., Ltd. group · JPY · fiscal-year flows",
    )
    _chart_block(
        "Calculated margins",
        charts.margin_chart(frame),
        caption="Profit ÷ net sales for the same fiscal year. Not a printed ratio line.",
    )

    grown = calc.add_yoy(frame, "net_sales_yen", [])
    grown = calc.add_yoy(grown, "operating_profit_yen", [])
    table = grown[[
        "fiscal_year_ending", "net_sales_yen", "net_sales_yen_growth",
        "operating_profit_yen", "operating_profit_yen_growth",
        "operating_margin_calculated", "profit_margin_calculated",
    ]].copy()
    for column in ("net_sales_yen_growth", "operating_profit_yen_growth", "operating_margin_calculated", "profit_margin_calculated"):
        table[column] = table[column].map(lambda v: "—" if pd.isna(v) else format_percent(float(v), 1))
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption("Growth is blank for the first year in the selected range and wherever a prior value is missing or zero. Margins are calculated from compatible annual flows in the same row.")

    margins = frame.dropna(subset=["operating_margin_calculated"]).sort_values("fiscal_year_ending")
    if len(margins) >= 2:
        first, last = margins.iloc[0], margins.iloc[-1]
        delta = float(last["operating_margin_calculated"] - first["operating_margin_calculated"])
        st.markdown(
            f'<div class="nih-note">Calculated operating margin moved {delta * 100:+.1f} percentage points between '
            f'{fiscal_label(int(first["fiscal_year_ending"]))} and {fiscal_label(int(last["fiscal_year_ending"]))} '
            f'in the selected range. That describes the two annual ratios; it does not attribute a cause.</div>',
            unsafe_allow_html=True,
        )
    with st.expander("Metrics that are not available"):
        for item in UNAVAILABLE_METRICS:
            st.markdown(f"- {item}")
    _definitions_expander(["net_sales_jpy", "operating_profit_jpy", "ordinary_profit_jpy", "profit_attributable_to_owners_jpy", "operating_margin_calculated", "profit_margin_calculated"])


# ---------------------------------------------------------------- page 5
def pipeline_health() -> None:
    components.header(
        st,
        "Pipeline health",
        "ETL operations and data quality",
        "Run history from meta.pipeline_runs. Historical annual disclosures are judged on their publication schedule, not on daily age.",
    )
    runs = _pipeline(20)
    counts = _counts()
    documents = _documents()
    if runs.empty:
        st.warning("No pipeline runs are recorded yet. Run `python -m nih pipeline run`.")
    else:
        latest = runs.iloc[0]
        status = str(latest["status"])
        st.markdown(components.status_pill(status), unsafe_allow_html=True)
        succeeded = runs[runs["status"] == "succeeded"]
        last_success = succeeded.iloc[0] if not succeeded.empty else None
        cards = st.columns(4)
        with cards[0]:
            components.kpi_card(st, "Latest run", status, str(latest["started_at"]))
        with cards[1]:
            components.kpi_card(st, "Last successful run", str(last_success["started_at"]) if last_success is not None else "None recorded", "From meta.pipeline_runs")
        with cards[2]:
            duration = latest.get("duration_seconds")
            components.kpi_card(st, "Latest duration", "—" if duration is None or pd.isna(duration) else f"{float(duration):.1f}s", f"dbt: {latest['dbt_status']}")
        with cards[3]:
            components.kpi_card(
                st,
                "Latest records",
                f"{format_count(latest['records_extracted'])} extracted",
                f"inserted {format_count(latest['records_inserted'])} · updated {format_count(latest['records_updated'])} · unchanged {format_count(latest['records_unchanged'])} · rejected {format_count(latest['records_rejected'])}",
            )
        history = runs[[
            "started_at", "status", "duration_seconds", "records_extracted", "records_inserted",
            "records_updated", "records_unchanged", "records_rejected", "dbt_status", "validation_failures",
        ]].copy()
        st.subheader("Execution history")
        st.dataframe(history, use_container_width=True, hide_index=True)
        failed = runs[runs["status"] == "failed"]
        if not failed.empty:
            st.subheader("Recent failures")
            for row in failed.head(3).itertuples():
                st.markdown(f'<span class="nih-status nih-bad">failed</span> {row.started_at} — {row.error_message or "No error text recorded"}', unsafe_allow_html=True)
        warnings: list[str] = []
        detail = latest.get("detail")
        if isinstance(detail, dict):
            warnings = [str(item) for item in detail.get("warnings") or []]
        if warnings:
            st.subheader("Optional source warnings")
            for warning in warnings:
                st.markdown(f'<div class="nih-note"><span class="nih-status nih-warn">warning</span> {warning}</div>', unsafe_allow_html=True)

    st.subheader("Official source freshness")
    from nih.pipeline import format_freshness, freshness_findings

    today = datetime.now(timezone.utc).date()
    dated = [(str(doc), as_of.date() if hasattr(as_of, "date") else as_of) for doc, as_of in documents]
    for line in format_freshness(dated, today):
        st.markdown(f"- {line}")
    findings = freshness_findings(dated, today)
    if findings:
        for finding in findings:
            st.warning(finding)
    else:
        st.success("No publication-schedule freshness finding. The quarterly marts being empty is expected and is not a freshness failure.")

    st.subheader("Dataset separation")
    cards = st.columns(3)
    with cards[0]:
        components.kpi_card(st, "Official unit rows", format_count(counts["official_unit_rows"]), "raw_official.unit_sales_disclosure")
    with cards[1]:
        components.kpi_card(st, "Official financial rows", format_count(counts["official_financial_rows"]), "raw_official.financial_line")
    with cards[2]:
        components.kpi_card(st, "Synthetic weekly rows", format_count(counts["simulated_rows"]), "raw_simulated only. Counted here for isolation; never used in the official pages.")
    st.caption("dbt tests require every official mart row to carry source_class = official_ir and fail if a synthetic label appears there.")


# ---------------------------------------------------------------- shell
def main() -> None:
    components.apply_style(st)
    with st.sidebar:
        st.markdown('<div class="nih-kicker">Nintendo Intelligence Hub</div>', unsafe_allow_html=True)
        st.caption("Internal-style BI portfolio")
        components.disclaimer(st)
        if queries.database_available():
            refreshed = _refresh()
            st.success("PostgreSQL: connected")
            st.caption(f"Most recent successful pipeline finish: {refreshed if refreshed is not None else 'not recorded'}")
            try:
                counts = _counts()
                st.caption(
                    f"Official rows: {counts['official_unit_rows'] + counts['official_financial_rows']:,} · "
                    f"Synthetic rows (separate): {counts['simulated_rows']:,}"
                )
            except Exception:
                st.caption("Warehouse counts unavailable.")
        else:
            st.error(
                "PostgreSQL is unavailable. Start it with `docker compose up -d --wait`, "
                "run `nih init-db`, then reload. No figures are shown from a substitute source."
            )
            st.stop()
        st.caption("Sources: Nintendo IR files loaded by `python -m nih pipeline run`. Synthetic data is isolated in raw_simulated.")

    navigation = st.navigation(
        [
            st.Page(executive_overview, title="Executive Overview", icon=":material/dashboard:", url_path="overview", default=True),
            st.Page(hardware_software, title="Hardware & Software", icon=":material/sports_esports:", url_path="platforms"),
            st.Page(regional_performance, title="Regional Performance", icon=":material/public:", url_path="regions"),
            st.Page(financial_intelligence, title="Financial Intelligence", icon=":material/payments:", url_path="financials"),
            st.Page(pipeline_health, title="Pipeline Health", icon=":material/monitoring:", url_path="pipeline"),
        ]
    )
    try:
        navigation.run()
    except queries.DashboardDataError as exc:
        st.error(f"Warehouse query failed. {exc} Check that PostgreSQL is running and `dbt build` has created the marts, then reload.")
    components.disclaimer(st)


if __name__ == "__main__":
    main()
