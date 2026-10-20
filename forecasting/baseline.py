"""Forecast baseline for synthetic weekly series."""

from __future__ import annotations

import pandas as pd

from nih.errors import ProvenanceError
from nih.provenance import assert_simulated_frame

MODEL_NAME = "sklearn.linear_regression.week_index"
DISCLAIMER = (
    "Forecast of a synthetic demonstration series. "
    "It is not a Nintendo outlook or result."
)


def fit_weekly_baseline(frame: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    """Fit a week-index line to each synthetic series and project `horizon` steps.

    The trainer rejects official disclosures. It is a foundation baseline,
    not a seasonal demand model.
    """

    if horizon < 1:
        raise ProvenanceError("horizon is a positive number of weeks")
    required = {"source_class", "series_name", "iso_year", "iso_week", "sku_code", "region_code", "units"}
    missing = required.difference(frame.columns)
    if missing:
        raise ProvenanceError(f"baseline input is missing {sorted(missing)}")
    assert_simulated_frame(set(frame["source_class"]), set(frame["series_name"]))

    from sklearn.linear_model import LinearRegression

    outputs: list[dict] = []
    grouped = frame.groupby(["series_name", "sku_code", "region_code"], dropna=False)
    for (series_name, sku_code, region_code), group in grouped:
        ordered = group.sort_values(["iso_year", "iso_week"])
        if len(ordered) < 2:
            raise ProvenanceError("the baseline trains on at least two weekly observations")
        regressor = LinearRegression()
        positions = [[position] for position in range(len(ordered))]
        regressor.fit(positions, ordered["units"].astype(float).to_numpy())
        future = [[len(ordered) + step] for step in range(horizon)]
        predictions = regressor.predict(future)
        for step, predicted in enumerate(predictions, start=1):
            outputs.append(
                {
                    "source_class": "simulated_operational",
                    "series_name": series_name,
                    "sku_code": sku_code,
                    "region_code": region_code,
                    "step": step,
                    "predicted_units": float(predicted),
                    "model_name": MODEL_NAME,
                    "disclaimer": DISCLAIMER,
                }
            )
    return pd.DataFrame(outputs)
