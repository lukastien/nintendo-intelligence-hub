"""Annual forecasting datasets built from the official reported marts.

Boundaries enforced here, before any model sees the data:

- annual flows only (``observation_type = 'annual_flow'``,
  ``period_span = 'fiscal_year'``); life-to-date snapshots never enter;
- worldwide rows only, one platform scope at a time;
- non-component scopes only (``include_in_cross_platform_total``), so a
  family total and its component models are never combined;
- synthetic rows are rejected: every input row must be ``official_ir``;
- missing fiscal years stay missing. They are reported in
  ``missing_years`` and are never filled with zero or interpolated
  values. A platform that did not report in a year is not a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from nih.config import Settings

PLATFORM_METRICS = ("hw_units_sell_in", "sw_units_sell_in")
FINANCIAL_METRICS = ("net_sales_yen", "operating_margin_calculated")


@dataclass(frozen=True)
class AnnualSeries:
    """One annual series: a platform/metric scope or a consolidated metric."""

    series_key: str
    metric_name: str
    platform: str
    platform_name: str
    years: tuple[int, ...]
    values: tuple[float, ...]
    missing_years: tuple[int, ...] = field(default_factory=tuple)
    provenance: str = "mart_reported"
    ended: bool = False

    @property
    def observations(self) -> int:
        return len(self.values)

    @property
    def first_year(self) -> int:
        return self.years[0]

    @property
    def last_year(self) -> int:
        return self.years[-1]


def build_series(annual: pd.DataFrame, financial: pd.DataFrame) -> list[AnnualSeries]:
    """Build eligible-shaped annual series from mart-shaped frames."""
    series: list[AnnualSeries] = []
    if not annual.empty:
        frame = annual.copy()
        if "source_class" in frame and not set(frame["source_class"].dropna()) <= {"official_ir"}:
            raise ValueError("forecasting datasets accept official_ir rows only")
        if "period_span" in frame:
            frame = frame[frame["period_span"] == "fiscal_year"]
        if "observation_type" in frame:
            frame = frame[frame["observation_type"] == "annual_flow"]
        if "region_code" in frame:
            frame = frame[frame["region_code"] == "GLOBAL"]
        if "include_in_cross_platform_total" in frame:
            frame = frame[frame["include_in_cross_platform_total"] == True]  # noqa: E712
        frame = frame[frame["metric_code"].isin(PLATFORM_METRICS)]
        frame = frame.dropna(subset=["value_units"])
        grouped = frame.groupby(["platform_code", "platform_name", "metric_code"], dropna=False)
        for (platform, name, metric), group in grouped:
            ordered = group.sort_values("fiscal_year_ending")
            years = tuple(int(y) for y in ordered["fiscal_year_ending"])
            values = tuple(float(v) for v in ordered["value_units"])
            series.append(
                AnnualSeries(
                    series_key=f"{platform}:{metric}",
                    metric_name=str(metric),
                    platform=str(platform),
                    platform_name=str(name),
                    years=years,
                    values=values,
                    missing_years=_missing_years(years),
                    provenance="mart_reported.mart_annual_platform_performance",
                )
            )
    if not financial.empty:
        frame = financial.sort_values("fiscal_year_ending")
        years = tuple(int(y) for y in frame["fiscal_year_ending"])
        for metric in FINANCIAL_METRICS:
            if metric not in frame:
                continue
            usable = frame.dropna(subset=[metric])
            series.append(
                AnnualSeries(
                    series_key=f"CONSOLIDATED:{metric}",
                    metric_name=metric,
                    platform="CONSOLIDATED",
                    platform_name="Nintendo Co., Ltd. consolidated",
                    years=tuple(int(y) for y in usable["fiscal_year_ending"]),
                    values=tuple(float(v) for v in usable[metric]),
                    missing_years=_missing_years(tuple(int(y) for y in usable["fiscal_year_ending"])),
                    provenance="mart_reported.mart_financial_performance",
                )
            )
    if series:
        latest = max(item.last_year for item in series)
        series = [
            item
            if item.platform == "CONSOLIDATED" or item.last_year >= latest
            else AnnualSeries(
                series_key=item.series_key,
                metric_name=item.metric_name,
                platform=item.platform,
                platform_name=item.platform_name,
                years=item.years,
                values=item.values,
                missing_years=item.missing_years,
                provenance=item.provenance,
                ended=True,
            )
            for item in series
        ]
    return sorted(series, key=lambda item: item.series_key)


def _missing_years(years: tuple[int, ...]) -> tuple[int, ...]:
    if len(years) < 2:
        return ()
    observed = set(years)
    return tuple(year for year in range(min(years), max(years) + 1) if year not in observed)


def load_datasets(settings: Settings | None = None) -> list[AnnualSeries]:
    """Load mart rows from PostgreSQL and build annual series."""
    from dashboards.queries import annual_performance, financial_performance

    annual = annual_performance(settings=settings)
    financial = financial_performance(settings=settings)
    return build_series(annual, financial)
