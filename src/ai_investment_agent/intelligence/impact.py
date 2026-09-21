from __future__ import annotations

import re
from dataclasses import dataclass

from ai_investment_agent.domain.enums import EventCategory, EventDirection, ImpactHorizon, VerificationStatus
from ai_investment_agent.domain.event_intelligence import ExtractedEntities, NormalizedEvent

_POSITIVE = re.compile(
    r"beat|surge|rally|ceasefire|upgrade|호실적|급등|흑자|개선|인상\s*동결",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"miss|plunge|downgrade|sanction|war|halt|적자|급락|제재|전쟁|거래정지|상장폐지|침공",
    re.IGNORECASE,
)
_HIGH_MAGNITUDE = re.compile(
    r"거래정지|상장폐지|war|missile|default|파산|halt|delist",
    re.IGNORECASE,
)

_HORIZON = {
    EventCategory.MACRO: ImpactHorizon.MONTHS,
    EventCategory.GEOPOLITICAL: ImpactHorizon.WEEKS,
    EventCategory.CORPORATE: ImpactHorizon.DAYS,
    EventCategory.INDUSTRY: ImpactHorizon.MONTHS,
    EventCategory.MARKET: ImpactHorizon.HOURS,
}

_TYPE_HORIZON = {
    "RATE_DECISION": ImpactHorizon.MONTHS,
    "INFLATION_PRINT": ImpactHorizon.WEEKS,
    "CONFLICT": ImpactHorizon.MONTHS,
    "SANCTION": ImpactHorizon.MONTHS,
    "LISTING_STATUS": ImpactHorizon.DAYS,
    "EARNINGS": ImpactHorizon.DAYS,
    "BOARD_MEETING": ImpactHorizon.HOURS,
}


@dataclass(frozen=True)
class ImpactAssessment:
    direction: EventDirection
    magnitude: float
    novelty: float
    confidence: float
    impact_horizon: ImpactHorizon
    summary: str


class ImpactAnalyzer:
    """Incident impact, not sentiment-as-trade. UNKNOWN is left UNKNOWN."""

    def analyze(
        self,
        members: list[NormalizedEvent],
        entities: ExtractedEntities,
        *,
        source_trust: float,
        verification: VerificationStatus,
        article_count: int,
        injection_blocked: bool,
    ) -> ImpactAssessment:
        blob = " ".join(f"{item.canonical_headline} {item.canonical_text}" for item in members)
        direction = _direction(blob, injection_blocked=injection_blocked)
        magnitude = 0.85 if _HIGH_MAGNITUDE.search(blob) else 0.35
        if direction is EventDirection.UNKNOWN:
            magnitude = min(magnitude, 0.2)
        if verification is VerificationStatus.RETRACTED:
            magnitude = min(magnitude, 0.15)
        novelty = round(1.0 / max(article_count, 1), 4)
        confidence = _confidence(source_trust, verification, direction, injection_blocked)
        horizon = _TYPE_HORIZON.get(entities.event_type, _HORIZON[entities.category or EventCategory.MARKET])
        summary = members[0].canonical_headline if members else ""
        return ImpactAssessment(
            direction=direction,
            magnitude=magnitude,
            novelty=novelty,
            confidence=confidence,
            impact_horizon=horizon,
            summary=summary,
        )


def _direction(blob: str, *, injection_blocked: bool) -> EventDirection:
    # Stripped jailbreak spans are already gone. Remaining text must independently support a label.
    pos = bool(_POSITIVE.search(blob))
    neg = bool(_NEGATIVE.search(blob))
    if pos and neg:
        return EventDirection.MIXED
    if pos:
        return EventDirection.POSITIVE
    if neg:
        return EventDirection.NEGATIVE
    if injection_blocked:
        return EventDirection.UNKNOWN
    return EventDirection.UNKNOWN


def _confidence(
    source_trust: float,
    verification: VerificationStatus,
    direction: EventDirection,
    injection_blocked: bool,
) -> float:
    multiplier = {
        VerificationStatus.VERIFIED: 1.0,
        VerificationStatus.PARTIALLY_VERIFIED: 0.75,
        VerificationStatus.UNVERIFIED: 0.4,
        VerificationStatus.RETRACTED: 0.15,
    }[verification]
    direction_factor = 0.55 if direction is EventDirection.UNKNOWN else 0.9
    injection_factor = 0.7 if injection_blocked else 1.0
    return round(max(0.0, min(1.0, source_trust * multiplier * direction_factor * injection_factor)), 4)
