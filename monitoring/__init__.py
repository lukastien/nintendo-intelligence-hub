"""Monitoring boundary for grain collisions and synthetic-series alerts.

The persistent monitoring layer lives in ``monitoring.engine`` (rules and
evaluations), ``monitoring.alerts`` (alert lifecycle), ``monitoring.anomalies``
(business movements), and ``monitoring.notifications``.
"""

from monitoring.checks import (
    aggregate_component_collisions,
    region_aggregate_collisions,
    simulated_zscore_alerts,
)

__all__ = [
    "aggregate_component_collisions",
    "region_aggregate_collisions",
    "simulated_zscore_alerts",
]
