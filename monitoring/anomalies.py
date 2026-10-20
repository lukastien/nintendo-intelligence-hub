"""Business anomaly detection over annual official flows.

Only annual flows are compared, only inside one platform scope, region,
and metric. Life-to-date rows never reach these functions (the callers
filter to the annual marts, and ``detect_*`` re-checks the span columns
when they are present). A launch year has no prior year and produces no
change; a missing prior value is a gap, never a zero.
"""

from __future__ import annotations

import pandas as pd

from monitoring.alerts import Finding
from monitoring.rules import Thresholds

ROBUST_Z_SCALE = 0.6745


def robust_z(value: float, history: list[float]) -> float | None:
    """Median/MAD robust z-score. None without variation or history."""
    if not history:
        return None
    series = pd.Series(history, dtype="float64")
    median = float(series.median())
    mad = float((series - median).abs().median())
    if mad == 0:
        return None
    return ROBUST_Z_SCALE * (float(value) - median) / mad


def detect_platform_anomalies(annual: pd.DataFrame, thresholds: Thresholds) -> list[Finding]:
    """YoY and robust-z findings for GLOBAL annual platform flows."""
    findings: list[Finding] = []
    frame = _annual_global(annual)
    if frame.empty:
        return findings
    for (platform, metric, region), group in frame.groupby(
        ["platform_code", "metric_code", "region_code"], dropna=False
    ):
        group = group.sort_values("fiscal_year_ending")
        values = [float(v) for v in group["value_units"].tolist()]
        years = [int(y) for y in group["fiscal_year_ending"].tolist()]
        names = group["platform_name"].tolist() if "platform_name" in group else [platform] * len(group)
        for index in range(1, len(group)):
            if years[index] != years[index - 1] + 1:
                continue  # A gap year is not a one-year change.
            prior, current = values[index - 1], values[index]
            if prior == 0:
                continue
            growth = (current - prior) / abs(prior)
            history = values[:index]
            score = None
            if len(history) >= thresholds.robust_min_history:
                score = robust_z(current, history)
            is_yoy = abs(growth) >= thresholds.yoy_change
            is_robust = score is not None and abs(score) >= thresholds.robust_z and is_yoy
            if not is_yoy and not is_robust:
                continue
            age = index + 1
            lifecycle = (
                " This platform scope has a short reported history, so a launch or early-lifecycle "
                "ramp is a plausible legitimate explanation."
                if age <= 2
                else ""
            )
            rule = "robust z-score" if is_robust else "year-over-year change"
            findings.append(
                Finding(
                    alert_type="robust_business_movement" if is_robust else "yoy_business_movement",
                    category="business",
                    severity="info",
                    source_name="mart_reported.mart_annual_platform_performance",
                    metric_name=str(metric),
                    platform=str(platform),
                    region=str(region),
                    reporting_period=f"FY3/{years[index]}",
                    observed_value=current,
                    expected_value=prior,
                    threshold=thresholds.robust_z if is_robust else thresholds.yoy_change,
                    explanation=(
                        f"{names[index]} {metric} changed {growth * 100:+.1f}% in FY3/{years[index]} "
                        f"versus FY3/{years[index - 1]} (annual sell-in, worldwide). "
                        + (
                            f"The robust z-score against the prior {len(history)} annual observations "
                            f"is {score:.2f} (median/MAD). "
                            if score is not None
                            else ""
                        )
                        + f"Detection rule: {rule}. This is a signal to investigate, "
                        "not evidence of a data error." + lifecycle
                    ),
                )
            )
    return findings


def detect_financial_anomalies(financial: pd.DataFrame, thresholds: Thresholds) -> list[Finding]:
    """YoY findings for consolidated flows and calculated margin moves."""
    findings: list[Finding] = []
    if financial.empty or "fiscal_year_ending" not in financial.columns:
        return findings
    frame = financial.sort_values("fiscal_year_ending")
    for column, label in (
        ("net_sales_yen", "Consolidated net sales"),
        ("operating_profit_yen", "Consolidated operating profit"),
    ):
        if column not in frame.columns:
            continue
        rows = frame[["fiscal_year_ending", column]].dropna()
        values = rows[column].tolist()
        years = [int(y) for y in rows["fiscal_year_ending"].tolist()]
        for index in range(1, len(rows)):
            if years[index] != years[index - 1] + 1:
                continue
            prior, current = float(values[index - 1]), float(values[index])
            if prior == 0:
                continue
            growth = (current - prior) / abs(prior)
            history = [float(v) for v in values[:index]]
            score = robust_z(current, history) if len(history) >= thresholds.robust_min_history else None
            if abs(growth) < thresholds.yoy_change and not (
                score is not None and abs(score) >= thresholds.robust_z and abs(growth) >= thresholds.yoy_change
            ):
                continue
            findings.append(
                Finding(
                    alert_type="financial_business_movement",
                    category="business",
                    severity="info",
                    source_name="mart_reported.mart_financial_performance",
                    metric_name=column,
                    reporting_period=f"FY3/{years[index]}",
                    observed_value=current,
                    expected_value=prior,
                    threshold=thresholds.yoy_change,
                    explanation=(
                        f"{label} changed {growth * 100:+.1f}% in FY3/{years[index]} versus "
                        f"FY3/{years[index - 1]} (consolidated Nintendo Co., Ltd., JPY). "
                        "Detection rule: year-over-year change. This describes a reported "
                        "movement; it does not attribute a cause or imply a data error."
                    ),
                )
            )
    if "operating_margin_calculated" in frame.columns:
        rows = frame[["fiscal_year_ending", "operating_margin_calculated"]].dropna()
        margins = rows["operating_margin_calculated"].tolist()
        years = [int(y) for y in rows["fiscal_year_ending"].tolist()]
        for index in range(1, len(rows)):
            if years[index] != years[index - 1] + 1:
                continue
            change = float(margins[index]) - float(margins[index - 1])
            if abs(change) < thresholds.margin_change_points:
                continue
            findings.append(
                Finding(
                    alert_type="margin_business_movement",
                    category="business",
                    severity="info",
                    source_name="mart_reported.mart_financial_performance",
                    metric_name="operating_margin_calculated",
                    reporting_period=f"FY3/{years[index]}",
                    observed_value=float(margins[index]),
                    expected_value=float(margins[index - 1]),
                    threshold=thresholds.margin_change_points,
                    explanation=(
                        f"Calculated operating margin moved {change * 100:+.1f} percentage points "
                        f"in FY3/{years[index]} versus FY3/{years[index - 1]} "
                        "(operating profit divided by consolidated net sales). Detection rule: "
                        "margin change. This is an observation, not a causal explanation."
                    ),
                )
            )
    return findings


def detect_regional_deviations(annual: pd.DataFrame, thresholds: Thresholds) -> list[Finding]:
    """Warning only when a complete breakdown deviates beyond precision.

    Known conditions are excluded upstream and here: incomplete layouts,
    exact matches, and differences within one printed unit.
    """
    findings: list[Finding] = []
    if annual.empty or "reconciliation_status" not in annual.columns:
        return findings
    rows = annual[
        (annual.get("region_code") == "GLOBAL")
        & (annual.get("reconciliation_status") == "differs")
    ] if "region_code" in annual.columns else annual.iloc[0:0]
    for row in rows.itertuples():
        global_units = getattr(row, "disclosed_global_units", None)
        parts = getattr(row, "regional_parts_sum", None)
        if global_units is None or parts is None or pd.isna(global_units) or pd.isna(parts):
            continue
        delta = abs(float(global_units) - float(parts))
        relative = delta / abs(float(global_units)) if float(global_units) != 0 else None
        if relative is None:
            continue
        if delta <= thresholds.regional_absolute_units or relative <= thresholds.regional_relative_deviation:
            continue
        findings.append(
            Finding(
                alert_type="regional_reconciliation_deviation",
                category="data_quality",
                severity="warning",
                source_name="mart_reported.mart_regional_performance",
                metric_name=str(getattr(row, "metric_code", "")),
                platform=str(getattr(row, "platform_code", "")),
                region="GLOBAL",
                reporting_period=f"FY3/{int(row.fiscal_year_ending)}",
                observed_value=float(parts),
                expected_value=float(global_units),
                threshold=thresholds.regional_relative_deviation,
                explanation=(
                    f"Regional parts sum to {float(parts):,.0f} versus a disclosed worldwide total of "
                    f"{float(global_units):,.0f} for FY3/{int(row.fiscal_year_ending)} "
                    f"({relative * 100:.3f}% deviation). Both figures are kept as printed; "
                    "investigate the source sheet rather than replacing either number."
                ),
            )
        )
    return findings


def _annual_global(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    if "period_span" in result.columns:
        result = result[result["period_span"] == "fiscal_year"]
    if "observation_type" in result.columns:
        result = result[result["observation_type"] == "annual_flow"]
    if "region_code" in result.columns:
        result = result[result["region_code"] == "GLOBAL"]
    if "include_in_cross_platform_total" in result.columns:
        result = result[result["include_in_cross_platform_total"] == True]  # noqa: E712
    result = result.dropna(subset=["value_units"])
    return result
