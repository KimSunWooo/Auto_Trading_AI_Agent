"""Confidence is a model self-score, not a probability.

calibratedConfidence is emitted only when an offline calibration table exists.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ai_investment_agent.domain.agent_views import AgentAssessment
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import HorizonChoice, Stance


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
    selected_agent_confidence: float | None = Field(default=None, ge=0, le=1)
    data_quality: float | None = Field(default=None, ge=0, le=1)
    market_regime_confidence: float | None = Field(default=None, ge=0, le=1)
    long_short_conflict: bool = False
    event_uncertainty: float | None = Field(default=None, ge=0, le=1)
    provenance: list[str] = Field(default_factory=list)


def compose_confidence(
    *,
    selected_choice: HorizonChoice,
    long_view: AgentAssessment,
    short_view: AgentAssessment,
    data_quality: float,
    market_regime_confidence: float,
    event_uncertainty: float = 0.0,
) -> ConfidenceAssessment:
    """Selected-agent confidence with explicit haircuts. Not min(long, short)."""

    if selected_choice is HorizonChoice.LONG_TERM:
        selected = long_view.confidence
        source = "long"
    elif selected_choice is HorizonChoice.SHORT_TERM:
        selected = short_view.confidence
        source = "short"
    else:
        selected = max(long_view.confidence, short_view.confidence)
        source = "unselected_max"

    conflict = {long_view.stance, short_view.stance} >= {Stance.BULLISH, Stance.BEARISH}
    conflict_factor = 0.85 if conflict else 1.0
    quality = _clip(data_quality)
    regime_factor = _clip(0.5 + 0.5 * market_regime_confidence)
    event_factor = _clip(1.0 - 0.5 * event_uncertainty)
    raw = _clip(selected * quality * regime_factor * conflict_factor * event_factor)
    provenance = [
        f"selectedAgent={source}",
        f"selectedAgentConfidence={selected:.4f}",
        f"dataQuality={quality:.4f}",
        f"marketRegimeConfidence={market_regime_confidence:.4f}",
        f"regimeFactor={regime_factor:.4f}",
        f"longShortConflict={conflict}",
        f"conflictFactor={conflict_factor:.4f}",
        f"eventUncertainty={event_uncertainty:.4f}",
        f"eventFactor={event_factor:.4f}",
        "rawConfidenceIsNotAProbability",
    ]
    return ConfidenceAssessment(
        raw_confidence=raw,
        calibrated_confidence=None,
        treated_as_probability=False,
        calibration_applied=False,
        selected_agent_confidence=selected,
        data_quality=quality,
        market_regime_confidence=_clip(market_regime_confidence),
        long_short_conflict=conflict,
        event_uncertainty=_clip(event_uncertainty),
        provenance=provenance,
    )
