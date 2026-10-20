"""Forecasting package.

Two strictly separated halves:

- ``baseline`` — the foundation synthetic weekly baseline. It rejects
  official data and must never be pointed at Nintendo disclosures.
- ``datasets`` / ``baselines`` / ``models`` / ``backtesting`` /
  ``evaluation`` / ``intervals`` / ``pipeline`` — Phase 7 annual
  forecasting over official marts only. It rejects synthetic rows,
  never writes to official facts or ``mart_reported``, and persists
  results in the ``forecast`` schema via ``python -m nih forecast run``.
"""

from forecasting.baseline import fit_weekly_baseline

__all__ = ["fit_weekly_baseline"]
