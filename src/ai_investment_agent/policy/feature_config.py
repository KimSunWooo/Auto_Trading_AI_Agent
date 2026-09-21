"""Configurable feature coefficients. Not hard-wired into calculators."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ai_investment_agent.domain.enums import EventCategory, ImpactHorizon


@dataclass(frozen=True)
class EventImpactWeights:
    """Exponents on the effectiveImpact product. Defaults reproduce:

    rawImpact × sourceTrust × relevance × novelty × confidence × timeDecay
    """

    raw_impact: float = 1.0
    source_trust: float = 1.0
    relevance: float = 1.0
    novelty: float = 1.0
    confidence: float = 1.0
    time_decay: float = 1.0


@dataclass(frozen=True)
class FeaturePolicyConfig:
    weights: EventImpactWeights = field(default_factory=EventImpactWeights)
    half_life: dict[ImpactHorizon, timedelta] = field(
        default_factory=lambda: {
            ImpactHorizon.MINUTES: timedelta(minutes=30),
            ImpactHorizon.HOURS: timedelta(hours=6),
            ImpactHorizon.DAYS: timedelta(days=2),
            ImpactHorizon.WEEKS: timedelta(days=7),
            ImpactHorizon.MONTHS: timedelta(days=30),
            ImpactHorizon.YEARS: timedelta(days=180),
        }
    )
    ticker_relevance: float = 1.0
    sector_relevance: float = 0.6
    category_relevance: dict[EventCategory, float] = field(
        default_factory=lambda: {
            EventCategory.MACRO: 0.8,
            EventCategory.GEOPOLITICAL: 0.85,
            EventCategory.CORPORATE: 0.35,
            EventCategory.INDUSTRY: 0.55,
            EventCategory.MARKET: 0.5,
        }
    )
    unmatched_relevance: float = 0.15
    event_risk_threshold: float = 0.45
    crisis_drawdown: float = 0.18
    high_vol_threshold: float = 0.025
    low_vol_threshold: float = 0.006
    low_liquidity_threshold: float = 0.3
    bull_return_threshold: float = 0.02
    bear_return_threshold: float = -0.02
    ma_short_window: int = 5
    ma_long_window: int = 20
    vol_window: int = 10
    min_bars_for_regime: int = 3
    priced_in_reaction_weight: float = 0.85
    priced_in_volume_weight: float = 0.15
    divergence_move_threshold: float = 0.01
    divergence_confidence_haircut: float = 0.35
    market_data_half_life: timedelta = timedelta(days=2)

    def effective_impact(
        self,
        *,
        raw_impact: float,
        source_trust: float,
        relevance: float,
        novelty: float,
        confidence: float,
        time_decay: float,
    ) -> float:
        weights = self.weights
        value = (
            (max(raw_impact, 0.0) ** weights.raw_impact)
            * (max(source_trust, 0.0) ** weights.source_trust)
            * (max(relevance, 0.0) ** weights.relevance)
            * (max(novelty, 0.0) ** weights.novelty)
            * (max(confidence, 0.0) ** weights.confidence)
            * (max(time_decay, 0.0) ** weights.time_decay)
        )
        return max(0.0, min(1.0, value))
