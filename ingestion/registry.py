"""Load and validate the source and metric catalogs."""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from ingestion.urls import assert_official_url, assert_simulated_url
from nih.config import project_root
from nih.errors import ProvenanceError
from nih.provenance import SourceClass


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_class: SourceClass
    publisher: str
    title: str
    url: str
    grain: str
    loads_measures_in_foundation: bool

    @model_validator(mode="after")
    def enforce_source_policy(self) -> "SourceRecord":
        if not self.grain.strip():
            raise ProvenanceError(f"{self.source_id} documents its grain")
        if self.source_class is SourceClass.OFFICIAL_IR:
            if self.publisher != "Nintendo Co., Ltd.":
                raise ProvenanceError("official_ir sources are published by Nintendo Co., Ltd.")
            assert_official_url(self.url)
            if self.loads_measures_in_foundation:
                raise ProvenanceError(
                    f"{self.source_id} stays unloaded in this foundation. "
                    "Official measures wait for a reviewed transcription."
                )
        elif self.source_class is SourceClass.SIMULATED_OPERATIONAL:
            if self.publisher != "SYNTHETIC":
                raise ProvenanceError("simulated sources use publisher SYNTHETIC")
            assert_simulated_url(self.url)
        elif self.source_class is SourceClass.PUBLIC_REFERENCE:
            if self.loads_measures_in_foundation:
                raise ProvenanceError("reference sources load attributes, not measures")
        return self


class MetricRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_code: str
    metric_name: str
    measure_family: Literal["unit_sales", "income_statement", "balance_sheet"]
    additive_flow: bool
    native_unit: Literal["units", "jpy"]
    sales_basis: Literal["sell_in", "not_applicable"]
    statement_scope: str
    comparability_note: str

    @model_validator(mode="after")
    def enforce_metric_policy(self) -> "MetricRecord":
        if not self.comparability_note.strip():
            raise ProvenanceError(f"{self.metric_code} has a comparability note")
        if self.measure_family == "balance_sheet" and self.additive_flow:
            raise ProvenanceError("balance-sheet metrics are stocks")
        if self.measure_family == "unit_sales":
            if self.sales_basis != "sell_in" or self.native_unit != "units":
                raise ProvenanceError("unit-sales metrics are sell-in units")
        elif self.native_unit != "jpy" or self.sales_basis != "not_applicable":
            raise ProvenanceError("financial metrics are yen amounts")
        return self


def _read_yaml(name: str) -> dict:
    path = project_root() / "config" / name
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ProvenanceError(f"{path} contains a mapping")
    return loaded


def load_source_catalog() -> list[SourceRecord]:
    payload = _read_yaml("sources.yaml")
    return [SourceRecord.model_validate(row) for row in payload["sources"]]


def load_metric_catalog() -> list[MetricRecord]:
    payload = _read_yaml("metrics.yaml")
    records = [MetricRecord.model_validate(row) for row in payload["metrics"]]
    codes = [record.metric_code for record in records]
    if len(codes) != len(set(codes)):
        raise ProvenanceError("metric codes are unique")
    return records
