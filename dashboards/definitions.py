"""Metric definitions shown in the dashboard and exported for Tableau.

These texts describe the official marts. They contain no sales figures.
"""

from __future__ import annotations

METRIC_DEFINITIONS: dict[str, dict[str, str]] = {
    "hw_units_sell_in": {
        "display_name": "Hardware units (sell-in)",
        "unit": "units",
        "source_mart": "mart_reported.mart_annual_platform_performance / mart_lifetime_platform_sales",
        "definition": (
            "Hardware sell-in for one platform scope. Annual rows are fiscal-year flows. "
            "Life-to-date rows are cumulative snapshots on an as-of date and are never annual sales."
        ),
        "caution": "A family total already includes its component models. Do not add them together.",
    },
    "sw_units_sell_in": {
        "display_name": "Software units (sell-in)",
        "unit": "units",
        "source_mart": "mart_reported.mart_annual_platform_performance / mart_lifetime_platform_sales",
        "definition": (
            "Software sell-in as defined by Nintendo IR for platform totals: packaged software and the "
            "downloadable edition of packaged software, including bundles. Download-only software and "
            "add-on content are outside this unit definition."
        ),
        "caution": "Top-selling title rows are inside the platform software total. Do not add them to it.",
    },
    "software_units_per_hardware_unit": {
        "display_name": "Software units per hardware unit",
        "unit": "ratio",
        "source_mart": "mart_reported.mart_hardware_software_trends",
        "definition": "Annual software units divided by annual hardware units for the same platform, region, and fiscal year.",
        "caution": "Blank when either metric is missing or hardware units are zero. It is a ratio of two annual flows, not an installed-base attach rate.",
    },
    "net_sales_jpy": {
        "display_name": "Net sales",
        "unit": "JPY",
        "source_mart": "mart_reported.mart_financial_performance",
        "definition": "Consolidated Nintendo Co., Ltd. net sales for the fiscal year, worldwide, in yen.",
        "caution": "Consolidated group result. It is not Nintendo of America revenue and not a platform split.",
    },
    "operating_profit_jpy": {
        "display_name": "Operating profit",
        "unit": "JPY",
        "source_mart": "mart_reported.mart_financial_performance",
        "definition": "Consolidated Nintendo Co., Ltd. operating profit for the fiscal year, in yen.",
        "caution": "Consolidated group result, not a regional or platform profit.",
    },
    "ordinary_profit_jpy": {
        "display_name": "Ordinary profit",
        "unit": "JPY",
        "source_mart": "mart_reported.mart_financial_performance",
        "definition": "Consolidated Nintendo Co., Ltd. ordinary profit for the fiscal year, in yen.",
        "caution": "Consolidated group result.",
    },
    "profit_attributable_to_owners_jpy": {
        "display_name": "Profit attributable to owners",
        "unit": "JPY",
        "source_mart": "mart_reported.mart_financial_performance",
        "definition": "Consolidated profit attributable to owners of the parent for the fiscal year, in yen.",
        "caution": "Consolidated group result.",
    },
    "operating_margin_calculated": {
        "display_name": "Operating margin (calculated)",
        "unit": "ratio",
        "source_mart": "mart_reported.mart_financial_performance",
        "definition": "Operating profit divided by net sales for the same fiscal year. Calculated in the mart; it is not a printed ratio line.",
        "caution": "Blank when net sales are zero or missing.",
    },
    "profit_margin_calculated": {
        "display_name": "Net profit margin (calculated)",
        "unit": "ratio",
        "source_mart": "mart_reported.mart_financial_performance",
        "definition": "Profit attributable to owners divided by net sales for the same fiscal year. Calculated in the mart.",
        "caution": "Blank when net sales are zero or missing.",
    },
    "regional_share": {
        "display_name": "Regional share of worldwide",
        "unit": "ratio",
        "source_mart": "mart_reported.mart_regional_performance",
        "definition": "One regional row divided by the disclosed worldwide total for the same platform, metric, and fiscal year, inside one region layout.",
        "caution": "Unavailable for an incomplete breakdown. Europe-split and Europe-inside-Other layouts are never combined.",
    },
}

UNAVAILABLE_METRICS: tuple[str, ...] = (
    "Quarterly unit sales and quarterly profit (no q1, q1_q2, or q1_q3 source columns are loaded)",
    "Sell-through, channel inventory, and retail stock",
    "Platform-level net sales in yen",
    "Gross profit, profit before tax, and printed profit ratios",
    "Nintendo of America standalone revenue or profit",
    "Annual sales for an individual software title (titles are life-to-date only)",
    "Forecasts",
)
