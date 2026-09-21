"""Apply offline calibration only when a table with data is present."""

from __future__ import annotations

from ai_investment_agent.domain.confidence import CalibrationTable


def resolve_calibrated(raw: float, table: CalibrationTable | None) -> float | None:
    """LLM raw scores are not probabilities.

    Missing calibration data yields None. This function never fabricates
    a calibrated value from the raw score alone.
    """

    if table is None or not table.has_data:
        return None
    return table.apply(raw)
