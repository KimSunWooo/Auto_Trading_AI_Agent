from __future__ import annotations

from datetime import datetime, timezone

from ai_investment_agent.domain.enums import MarketRegimeType
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot


class RegimeAssessor:
    """Fixture-era regime assessment. Defaults to UNKNOWN when evidence is weak."""

    def assess(
        self,
        snapshot: MarketSnapshot,
        events: list[MarketEvent],
        as_of: datetime | None = None,
    ) -> MarketRegime:
        now = as_of or snapshot.as_of
        if snapshot.regime_hint is not None:
            hint = snapshot.regime_hint
            if hint is MarketRegimeType.UNKNOWN:
                return MarketRegime(
                    regime=MarketRegimeType.UNKNOWN,
                    confidence=0.0,
                    as_of=now,
                    explanation="Regime hint is UNKNOWN. NO_TRADE is the required outcome.",
                    detected_from="fixture-hint",
                )
            return MarketRegime(
                regime=hint,
                confidence=0.6,
                as_of=now,
                explanation=f"Fixture-provided regime hint: {hint.value}",
                detected_from="fixture-hint",
            )

        if snapshot.last_price is None or snapshot.data_completeness < 0.3:
            return MarketRegime(
                regime=MarketRegimeType.UNKNOWN,
                confidence=0.0,
                as_of=now,
                explanation="Insufficient market data; regime cannot be classified.",
                detected_from="completeness-gate",
            )

        critical = [event for event in events if event.severity.value == "CRITICAL"]
        if critical:
            return MarketRegime(
                regime=MarketRegimeType.UNKNOWN,
                confidence=0.2,
                as_of=now,
                explanation="Critical events present without a production regime model.",
                detected_from="event-fallback",
            )

        return MarketRegime(
            regime=MarketRegimeType.UNKNOWN,
            confidence=0.0,
            as_of=now,
            explanation="No production regime model is connected. Default is UNKNOWN.",
            detected_from="safe-default",
        )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
