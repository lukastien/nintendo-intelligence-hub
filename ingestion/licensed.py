"""Optional public sales file with an explicit license.

No dataset is bundled. A missing manifest is an unavailable source, not a
cue to generate rows.
"""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

from ingestion.records import SourceOutcome

REQUIRED_MANIFEST = ("license_name", "license_url", "source_url", "file")
REQUIRED_COLUMNS = ("title", "platform", "region", "period_label", "units", "measurement_type")


def licensed_outcome(root: Path) -> SourceOutcome:
    folder = root / "raw" / "manual" / "licensed_public_sales"
    manifest_path = folder / "manifest.yaml"
    if not manifest_path.exists():
        return SourceOutcome(
            source_id="licensed_public_sales",
            source_class="public_reference",
            status="unavailable",
            accepted=0,
            rejected=0,
            missing=0,
            message=(
                "No licensed public sales file is configured. Place a manifest at "
                "data/raw/manual/licensed_public_sales/manifest.yaml with license_name, "
                "license_url, source_url, and file. Third-party charts without a "
                "redistribution license are not downloaded. No rows were substituted."
            ),
        )
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or any(not str(payload.get(key, "")).strip() for key in REQUIRED_MANIFEST):
        return SourceOutcome(
            source_id="licensed_public_sales",
            source_class="public_reference",
            status="failed",
            accepted=0,
            rejected=0,
            missing=0,
            message="The license manifest is missing license_name, license_url, source_url, or file.",
        )
    source_file = folder / str(payload["file"])
    if not source_file.is_file():
        return SourceOutcome(
            source_id="licensed_public_sales",
            source_class="public_reference",
            status="unavailable",
            accepted=0,
            rejected=0,
            missing=0,
            message=f"The manifest names {payload['file']}, and that file is not in the manual folder.",
        )
    with source_file.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        if missing_columns:
            return SourceOutcome(
                source_id="licensed_public_sales",
                source_class="public_reference",
                status="failed",
                accepted=0,
                rejected=0,
                missing=0,
                message=f"The licensed file is missing columns: {', '.join(missing_columns)}.",
            )
        accepted = 0
        missing = 0
        cleaned_dir = root / "cleaned" / "public_reference"
        cleaned_dir.mkdir(parents=True, exist_ok=True)
        destination = cleaned_dir / "licensed_public_sales.csv"
        with destination.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "license_name",
                    "license_url",
                    "source_url",
                    *REQUIRED_COLUMNS,
                ],
            )
            writer.writeheader()
            for row in reader:
                if not (row.get("units") or "").strip():
                    missing += 1
                    continue
                writer.writerow(
                    {
                        "license_name": payload["license_name"],
                        "license_url": payload["license_url"],
                        "source_url": payload["source_url"],
                        **{column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS},
                    }
                )
                accepted += 1
    return SourceOutcome(
        source_id="licensed_public_sales",
        source_class="public_reference",
        status="loaded" if accepted else "failed",
        accepted=accepted,
        rejected=0,
        missing=missing,
        message=(
            f"Loaded {accepted} licensed public rows under {payload['license_name']}. "
            "These rows stay out of raw_official."
            if accepted
            else "The licensed file had no unit values."
        ),
    )
