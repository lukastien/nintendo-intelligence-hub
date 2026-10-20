"""Source classes and the boundary around reported marts."""

from enum import Enum

from nih.errors import ProvenanceError


class SourceClass(str, Enum):
    OFFICIAL_IR = "official_ir"
    PUBLIC_REFERENCE = "public_reference"
    SIMULATED_OPERATIONAL = "simulated_operational"


def assert_reported_mart_source(source_class: SourceClass) -> None:
    """Reported marts accept Nintendo IR disclosures only."""

    if source_class is not SourceClass.OFFICIAL_IR:
        raise ProvenanceError(
            f"{source_class.value} stays out of reported marts. "
            "Reported marts accept official_ir disclosures."
        )


def assert_simulated_frame(source_classes: set[str], series_names: set[str]) -> None:
    """Forecasting and anomaly checks accept the synthetic series only."""

    if source_classes != {SourceClass.SIMULATED_OPERATIONAL.value}:
        raise ProvenanceError(
            "This operation accepts simulated_operational rows. "
            f"Received {sorted(source_classes)}."
        )
    foreign = sorted(name for name in series_names if not str(name).startswith("synthetic_"))
    if foreign:
        raise ProvenanceError(
            "Simulated series names start with 'synthetic_'. "
            f"Received {foreign}."
        )
