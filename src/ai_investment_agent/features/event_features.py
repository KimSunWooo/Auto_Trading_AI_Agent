from __future__ import annotations

from datetime import datetime

from ai_investment_agent.domain.context import EventImpactFeatures
from ai_investment_agent.domain.enums import EventCategory
from ai_investment_agent.domain.event_intelligence import AnalyzedMarketEvent
from ai_investment_agent.features.mathutil import clip01
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig


class EventFeatureCalculator:
    """Deterministic event features, including time decay of impact."""

    def __init__(self, config: FeaturePolicyConfig | None = None) -> None:
        self.config = config or FeaturePolicyConfig()

    def compute(
        self,
        events: list[AnalyzedMarketEvent],
        *,
        ticker: str,
        as_of: datetime,
        sectors: list[str] | None = None,
        confidence_haircut: float = 0.0,
    ) -> EventImpactFeatures:
        if not events:
            return EventImpactFeatures(
                raw_impact=0.0,
                source_trust=0.0,
                relevance=0.0,
                novelty=0.0,
                event_confidence=0.0,
                time_decay=1.0,
                effective_impact=0.0,
                macro_risk=0.0,
                geopolitical_risk=0.0,
                sector_risk=0.0,
                company_event_risk=0.0,
                event_magnitude=0.0,
            )

        scored = [self._score(event, ticker=ticker, as_of=as_of, sectors=sectors or []) for event in events]
        dominant = max(scored, key=lambda item: item["effective_impact"])
        haircut = clip01(1.0 - confidence_haircut)
        confidence = clip01(dominant["event_confidence"] * haircut)
        effective = self.config.effective_impact(
            raw_impact=dominant["raw_impact"],
            source_trust=dominant["source_trust"],
            relevance=dominant["relevance"],
            novelty=dominant["novelty"],
            confidence=confidence,
            time_decay=dominant["time_decay"],
        )
        return EventImpactFeatures(
            raw_impact=dominant["raw_impact"],
            source_trust=dominant["source_trust"],
            relevance=dominant["relevance"],
            novelty=dominant["novelty"],
            event_confidence=confidence,
            time_decay=dominant["time_decay"],
            effective_impact=effective,
            macro_risk=_max_for(scored, EventCategory.MACRO),
            geopolitical_risk=_max_for(scored, EventCategory.GEOPOLITICAL),
            sector_risk=_max_for(scored, EventCategory.INDUSTRY),
            company_event_risk=_max_for(scored, EventCategory.CORPORATE),
            event_magnitude=max(event.magnitude for event in events),
            dominant_category=dominant["category"],
            dominant_direction=dominant["direction"],
            dominant_event_id=dominant["event_id"],
        )

    def _score(
        self,
        event: AnalyzedMarketEvent,
        *,
        ticker: str,
        as_of: datetime,
        sectors: list[str],
    ) -> dict:
        relevance = self.relevance_for(event, ticker=ticker, sectors=sectors)
        decay = self.time_decay_for(event, as_of)
        effective = self.config.effective_impact(
            raw_impact=event.magnitude,
            source_trust=event.source_trust,
            relevance=relevance,
            novelty=event.novelty,
            confidence=event.confidence,
            time_decay=decay,
        )
        return {
            "event_id": event.event_id,
            "category": event.category,
            "direction": event.direction,
            "raw_impact": event.magnitude,
            "source_trust": event.source_trust,
            "relevance": relevance,
            "novelty": event.novelty,
            "event_confidence": event.confidence,
            "time_decay": decay,
            "effective_impact": effective,
        }

    def relevance_for(
        self,
        event: AnalyzedMarketEvent,
        *,
        ticker: str,
        sectors: list[str],
    ) -> float:
        cfg = self.config
        if ticker in event.tickers:
            return cfg.ticker_relevance
        if sectors and set(sectors).intersection(event.sectors):
            return cfg.sector_relevance
        return cfg.category_relevance.get(event.category, cfg.unmatched_relevance)

    def time_decay_for(self, event: AnalyzedMarketEvent, as_of: datetime) -> float:
        age = as_of - event.analyzed_at
        seconds = age.total_seconds()
        if seconds < 0:
            return 0.0
        half = self.config.half_life[event.impact_horizon].total_seconds() or 1.0
        return clip01(0.5 ** (seconds / half))


def _max_for(scored: list[dict], category: EventCategory) -> float:
    values = [item["effective_impact"] for item in scored if item["category"] is category]
    return max(values) if values else 0.0
