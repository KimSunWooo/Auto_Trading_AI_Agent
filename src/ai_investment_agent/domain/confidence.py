"""Confidence is a model self-score, not a probability.

calibratedConfidence is emitted only when an offline calibration table exists.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel


def _clip(value: float) -> float:
    return min(1.0, max(0.0, value))


class CalibrationTable(DomainModel):
    """Offline reliability map: raw score → calibrated score.

    An empty table means calibration data is missing. Callers must not
    invent a calibrated value in that case.
    """

    pairs: tuple[tuple[float, float], ...] = ()

    @property
    def has_data(self) -> bool:
        return len(self.pairs) > 0

    def apply(self, raw: float) -> float | None:
        if not self.has_data:
            return None
        ordered = sorted(self.pairs, key=lambda item: item[0])
        if raw <= ordered[0][0]:
            return _clip(ordered[0][1])
        if raw >= ordered[-1][0]:
            return _clip(ordered[-1][1])
        for left, right in zip(ordered, ordered[1:]):
            if left[0] <= raw <= right[0]:
                span = right[0] - left[0]
                if span == 0:
                    return _clip(left[1])
                weight = (raw - left[0]) / span
                return _clip(left[1] + weight * (right[1] - left[1]))
        return _clip(ordered[-1][1])


class ConfidenceAssessment(DomainModel):
    raw_confidence: float = Field(ge=0, le=1)
    calibrated_confidence: float | None = Field(default=None, ge=0, le=1)
    treated_as_probability: Literal[False] = False
    calibration_applied: bool = False
