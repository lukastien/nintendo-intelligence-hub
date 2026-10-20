"""Printed Nintendo labels mapped to warehouse codes.

Unmapped names are rejected by the parser. A code is not guessed from a
figure, and a missing region is not filled in.
"""

from __future__ import annotations

from ingestion.classify import normalize_label

# code, is_platform_aggregate
FAMILY_PLATFORMS: dict[str, tuple[str, bool]] = {
    "family computer/nes": ("FC_NES", False),
    "game boy": ("GB", False),
    "game boy advance": ("GBA", True),
    "super family computer/snes": ("SNES", False),
    "nintendo 64": ("N64", False),
    "nintendo gamecube": ("NGC", False),
    "nintendo ds": ("NDS_FAMILY", True),
    "wii": ("WII", False),
    "nintendo 3ds": ("N3DS_FAMILY", True),
    "wii u": ("WIIU", False),
    "nintendo switch": ("NSW_FAMILY", True),
    "nintendo switch 2": ("NS2", False),
}

# code, parent platform code
COMPONENT_PLATFORMS: dict[str, tuple[str, str]] = {
    "game boy advance sp": ("GBA_SP", "GBA"),
    "nintendo ds lite": ("NDS_LITE", "NDS_FAMILY"),
    "nintendo dsi": ("NDS_DSI", "NDS_FAMILY"),
    "nintendo dsi xl": ("NDS_DSIXL", "NDS_FAMILY"),
    "nintendo 3ds xl": ("N3DS_XL", "N3DS_FAMILY"),
    "nintendo 2ds": ("N2DS", "N3DS_FAMILY"),
    "new nintendo 3ds": ("N3DS_NEW", "N3DS_FAMILY"),
    "new nintendo 3ds xl": ("N3DS_NEW_XL", "N3DS_FAMILY"),
    "new nintendo 2ds xl": ("N2DS_XL", "N3DS_FAMILY"),
    "nintendo switch": ("NSW", "NSW_FAMILY"),
    "nintendo switch - oled model": ("NSOLED", "NSW_FAMILY"),
    "nintendo switch lite": ("NSLITE", "NSW_FAMILY"),
}

# code, is_region_aggregate
REGIONS: dict[str, tuple[str, bool]] = {
    "japan": ("JPN", False),
    "the americas": ("AMR", False),
    "europe": ("EUR", False),
    "other": ("OTH", False),
    "total": ("GLOBAL", True),
}

INCOME_METRICS: dict[str, str] = {
    "net sales": "net_sales_jpy",
    "operating profit": "operating_profit_jpy",
    "ordinary profit": "ordinary_profit_jpy",
    "profit attributable to owners of parent": "profit_attributable_to_owners_jpy",
}

TITLE_PAGE_PLATFORMS: dict[str, tuple[str, bool]] = {
    "switch2": ("NS2", False),
    "switch": ("NSW_FAMILY", True),
    "wiiu": ("WIIU", False),
    "3ds": ("N3DS_FAMILY", True),
}


def family_platform(label: str) -> tuple[str, bool] | None:
    return FAMILY_PLATFORMS.get(normalize_label(label))


def component_platform(label: str) -> tuple[str, str] | None:
    folded = normalize_label(label)
    if folded.startswith("of which "):
        folded = folded[len("of which ") :]
    return COMPONENT_PLATFORMS.get(folded)


def region(label: str, *, europe_is_split: bool) -> tuple[str, bool, str] | None:
    """Return region code, aggregate flag, and a comparability note."""

    found = REGIONS.get(normalize_label(label))
    if found is None:
        return None
    code, aggregate = found
    note = ""
    if code == "OTH" and not europe_is_split:
        code = "OTH_INCL_EUROPE"
        note = (
            "This sheet prints Japan, the Americas, and Other. "
            "Europe is not a separate column, so Other includes Europe."
        )
    return code, aggregate, note
