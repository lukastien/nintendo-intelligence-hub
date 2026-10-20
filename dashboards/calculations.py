"""KPI and insight calculations over mart-shaped DataFrames.

Every function is pure: it takes rows that came from SQL and returns new
frames or scalars. Missing values stay missing. A growth rate needs the
same platform scope in both years, so a platform launch or retirement is
not reported as growth of a continuing total.
"""

from __future__ import annotations

import pandas as pd

ANNUAL = "annual_flow"
LIFETIME = "point_in_time_cumulative"


def filter_annual(frame: pd.DataFrame, *, fiscal_years=None, platforms=None, regions=None, metrics=None) -> pd.DataFrame:
    result = _filter(frame, fiscal_years=fiscal_years, platforms=platforms, regions=regions, metrics=metrics)
    if "observation_type" in result.columns:
        result = result[result["observation_type"] == ANNUAL]
    if "period_span" in result.columns:
        result = result[result["period_span"] == "fiscal_year"]
    return result.reset_index(drop=True)


def filter_lifetime(frame: pd.DataFrame, *, platforms=None, regions=None, metrics=None, latest_only: bool = False) -> pd.DataFrame:
    result = _filter(frame, platforms=platforms, regions=regions, metrics=metrics)
    if "observation_type" in result.columns:
        result = result[result["observation_type"] == LIFETIME]
    if "period_span" in result.columns:
        result = result[result["period_span"] == "life_to_date"]
    if latest_only and "is_latest_as_of" in result.columns:
        result = result[result["is_latest_as_of"] == True]  # noqa: E712 - pandas mask
    return result.reset_index(drop=True)


def _filter(frame, *, fiscal_years=None, platforms=None, regions=None, metrics=None) -> pd.DataFrame:
    result = frame.copy()
    if fiscal_years is not None and "fiscal_year_ending" in result.columns:
        years = [fiscal_years] if isinstance(fiscal_years, (int, float)) else list(fiscal_years)
        result = result[result["fiscal_year_ending"].isin(years)]
    if platforms is not None and "platform_code" in result.columns:
        codes = [platforms] if isinstance(platforms, str) else list(platforms)
        result = result[result["platform_code"].isin(codes)]
    if regions is not None and "region_code" in result.columns:
        codes = [regions] if isinstance(regions, str) else list(regions)
        result = result[result["region_code"].isin(codes)]
    if metrics is not None and "metric_code" in result.columns:
        codes = [metrics] if isinstance(metrics, str) else list(metrics)
        result = result[result["metric_code"].isin(codes)]
    return result


def cross_platform_total(frame: pd.DataFrame, fiscal_year: int, metric_code: str, region_code: str = "GLOBAL") -> float | None:
    """Sum one annual metric across non-component platforms for one region.

    Family totals are included once. Component models and the worldwide
    row's regional siblings are excluded by the caller-visible filters.
    """
    rows = filter_annual(frame, fiscal_years=fiscal_year, regions=region_code, metrics=metric_code)
    if "include_in_cross_platform_total" in rows.columns:
        rows = rows[rows["include_in_cross_platform_total"] == True]  # noqa: E712
    if rows.empty or rows["value_units"].isna().all():
        return None
    return float(rows["value_units"].sum(min_count=1))


def comparable_yoy(frame: pd.DataFrame, fiscal_year: int, metric_code: str, region_code: str = "GLOBAL") -> dict | None:
    """Year-over-year change only when the platform set is identical.

    Returns None when the prior year is absent, either total is missing,
    the prior total is zero, or the set of reporting platforms changed.
    """
    current_rows = _platform_values(frame, fiscal_year, metric_code, region_code)
    prior_rows = _platform_values(frame, fiscal_year - 1, metric_code, region_code)
    if current_rows is None or prior_rows is None:
        return None
    if set(current_rows) != set(prior_rows):
        return None
    current = float(sum(current_rows.values()))
    prior = float(sum(prior_rows.values()))
    if prior == 0:
        return None
    return {
        "fiscal_year_ending": fiscal_year,
        "current": current,
        "prior": prior,
        "change": current - prior,
        "growth": (current - prior) / abs(prior),
        "platform_count": len(current_rows),
    }


def _platform_values(frame, fiscal_year, metric_code, region_code) -> dict[str, float] | None:
    rows = filter_annual(frame, fiscal_years=fiscal_year, regions=region_code, metrics=metric_code)
    if "include_in_cross_platform_total" in rows.columns:
        rows = rows[rows["include_in_cross_platform_total"] == True]  # noqa: E712
    if rows.empty:
        return None
    values: dict[str, float] = {}
    for _, row in rows.iterrows():
        value = row.get("value_units")
        if value is None or pd.isna(value):
            return None
        code = str(row.get("platform_code", ""))
        if code in values:
            return None
        values[code] = float(value)
    return values or None


def platform_leader(frame: pd.DataFrame, fiscal_year: int, metric_code: str, region_code: str = "GLOBAL") -> dict | None:
    rows = filter_annual(frame, fiscal_years=fiscal_year, regions=region_code, metrics=metric_code)
    if "include_in_cross_platform_total" in rows.columns:
        rows = rows[rows["include_in_cross_platform_total"] == True]  # noqa: E712
    rows = rows.dropna(subset=["value_units"])
    if rows.empty:
        return None
    top = rows.sort_values("value_units", ascending=False).iloc[0]
    return {
        "platform_code": str(top["platform_code"]),
        "platform_name": str(top.get("platform_name", top["platform_code"])),
        "value_units": float(top["value_units"]),
        "fiscal_year_ending": int(fiscal_year),
    }


def largest_yoy_change(frame: pd.DataFrame, fiscal_year: int, metric_code: str, region_code: str = "GLOBAL") -> dict | None:
    """Largest absolute per-platform growth where both years are reported."""
    rows = filter_annual(frame, fiscal_years=[fiscal_year, fiscal_year - 1], regions=region_code, metrics=metric_code)
    if rows.empty:
        return None
    best: dict | None = None
    for platform, group in rows.groupby("platform_code"):
        by_year = {int(r["fiscal_year_ending"]): r for _, r in group.iterrows()}
        if fiscal_year not in by_year or fiscal_year - 1 not in by_year:
            continue
        current = by_year[fiscal_year].get("value_units")
        prior = by_year[fiscal_year - 1].get("value_units")
        if current is None or prior is None or pd.isna(current) or pd.isna(prior) or float(prior) == 0:
            continue
        growth = (float(current) - float(prior)) / abs(float(prior))
        candidate = {
            "platform_code": str(platform),
            "platform_name": str(by_year[fiscal_year].get("platform_name", platform)),
            "growth": growth,
            "current": float(current),
            "prior": float(prior),
        }
        if best is None or abs(candidate["growth"]) > abs(best["growth"]):
            best = candidate
    return best


def add_yoy(frame: pd.DataFrame, value_column: str, group_columns: list[str]) -> pd.DataFrame:
    """Append prior value, change, and growth, sorted by group and year.

    Growth is blank for the first year of a group, for a zero prior value,
    and for any missing value. It never fills a missing year with zero.
    """
    result = frame.copy().sort_values([*group_columns, "fiscal_year_ending"]).reset_index(drop=True)
    if group_columns:
        grouped = result.groupby(group_columns, dropna=False)[value_column]
        result[f"{value_column}_prior"] = grouped.shift(1)
    else:
        result[f"{value_column}_prior"] = result[value_column].shift(1)
    result[f"{value_column}_change"] = result[value_column] - result[f"{value_column}_prior"]
    prior = result[f"{value_column}_prior"]
    growth = result[f"{value_column}_change"] / prior.abs()
    result[f"{value_column}_growth"] = growth.where(prior.notna() & (prior != 0))
    return result


def software_hardware_ratio(hardware_units, software_units) -> float | None:
    if hardware_units is None or software_units is None:
        return None
    try:
        hardware = float(hardware_units)
        software = float(software_units)
    except (TypeError, ValueError):
        return None
    if pd.isna(hardware) or pd.isna(software) or hardware == 0:
        return None
    return software / hardware


def margin(numerator, denominator) -> float | None:
    if numerator is None or denominator is None:
        return None
    try:
        top = float(numerator)
        bottom = float(denominator)
    except (TypeError, ValueError):
        return None
    if pd.isna(top) or pd.isna(bottom) or bottom == 0:
        return None
    return top / bottom


def regional_share(value_units, disclosed_global_units, reconciliation_status: str | None) -> float | None:
    """Share of the disclosed worldwide total, inside one region layout."""
    if reconciliation_status == "incomplete_breakdown":
        return None
    if value_units is None or disclosed_global_units is None:
        return None
    try:
        value = float(value_units)
        total = float(disclosed_global_units)
    except (TypeError, ValueError):
        return None
    if pd.isna(value) or pd.isna(total) or total == 0:
        return None
    return value / total


def add_regional_share(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        result["regional_share"] = pd.Series(dtype="float64")
        return result
    result["regional_share"] = [
        regional_share(value, total, status)
        for value, total, status in zip(
            result.get("value_units", []),
            result.get("disclosed_global_units", []),
            result.get("reconciliation_status", []),
            strict=False,
        )
    ]
    return result


def financial_for_year(frame: pd.DataFrame, fiscal_year: int) -> dict | None:
    rows = frame[frame["fiscal_year_ending"] == fiscal_year] if "fiscal_year_ending" in frame.columns else frame.iloc[0:0]
    if rows.empty:
        return None
    row = rows.iloc[0]
    def number(column):
        value = row.get(column)
        return None if value is None or pd.isna(value) else float(value)
    return {
        "fiscal_year_ending": int(fiscal_year),
        "net_sales_yen": number("net_sales_yen"),
        "operating_profit_yen": number("operating_profit_yen"),
        "ordinary_profit_yen": number("ordinary_profit_yen"),
        "profit_attributable_to_owners_yen": number("profit_attributable_to_owners_yen"),
        "operating_margin": number("operating_margin_calculated"),
        "profit_margin": number("profit_margin_calculated"),
    }


def executive_insights(annual: pd.DataFrame, financial: pd.DataFrame, fiscal_year: int) -> list[str]:
    """Descriptive observations only. No cause is claimed."""
    insights: list[str] = []
    leader = platform_leader(annual, fiscal_year, "hw_units_sell_in")
    if leader:
        from dashboards.formatting import fiscal_label, format_units
        insights.append(
            f"In {fiscal_label(fiscal_year)}, {leader['platform_name']} reported the highest annual "
            f"hardware sell-in among non-component platform scopes, at {format_units(leader['value_units'])} worldwide. "
            "That is a ranking of disclosed annual flows, not an explanation for the result."
        )
    change = largest_yoy_change(annual, fiscal_year, "hw_units_sell_in")
    if change:
        from dashboards.formatting import fiscal_label, format_percent
        insights.append(
            f"The largest per-platform hardware change versus {fiscal_label(fiscal_year - 1)} was "
            f"{change['platform_name']} at {format_percent(change['growth'])}. Platforms without both years are excluded."
        )
    fin = financial_for_year(financial, fiscal_year)
    prior = financial_for_year(financial, fiscal_year - 1)
    if fin and prior and fin["operating_margin"] is not None and prior["operating_margin"] is not None:
        from dashboards.formatting import fiscal_label, format_percent
        delta = fin["operating_margin"] - prior["operating_margin"]
        insights.append(
            f"Calculated operating margin moved {delta * 100:+.1f} percentage points versus {fiscal_label(fiscal_year - 1)} "
            f"({format_percent(fin['operating_margin'])} in {fiscal_label(fiscal_year)}). "
            "The margin is operating profit divided by consolidated net sales."
        )
    if not insights:
        insights.append("No comparable annual observation is available for the selected fiscal year.")
    return insights
