"""Market context and feature snapshots. Not a trade proposal."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import (
    ContextSignal,
    EventCategory,
    EventDirection,
    MarketRegimeType,
)
from ai_investment_agent.domain.market import MarketRegime
from ai_investment_agent.domain.versions import CONTEXT_FEATURE_VERSION, POLICY_VERSION


class PriceSeries(DomainModel):
    """Observed market path. Missing points stay missing; nothing is imputed."""

    timestamps: list[datetime] = Field(default_factory=list)
    closes: list[Decimal] = Field(default_factory=list)
    volumes: list[Decimal] = Field(default_factory=list)
    highs: list[Decimal] | None = None
    lows: list[Decimal] | None = None

    @model_validator(mode="after")
    def check_alignment(self) -> PriceSeries:
        if len(self.timestamps) != len(self.closes):
            raise ValueError("timestamps and closes must be the same length")
        if self.volumes and len(self.volumes) != len(self.closes):
            raise ValueError("volumes must align with closes")
        return self


class QuantitativeFeatures(DomainModel):
    return_1d: Decimal | None = None
    return_5d: Decimal | None = None
    ma_short: Decimal | None = None
    ma_long: Decimal | None = None
    momentum: Decimal | None = None
    volatility: Decimal | None = None
    drawdown: Decimal | None = None
    volume_ratio: Decimal | None = None
    liquidity: Decimal | None = None
    trend: Decimal | None = None
    relative_strength: Decimal | None = None
    time_decay: Decimal | None = None


class EventImpactFeatures(DomainModel):
    raw_impact: float = Field(ge=0, le=1)
    source_trust: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    event_confidence: float = Field(ge=0, le=1)
    time_decay: float = Field(ge=0, le=1)
    effective_impact: float = Field(ge=0, le=1)
    macro_risk: float = Field(ge=0, le=1)
    geopolitical_risk: float = Field(ge=0, le=1)
    sector_risk: float = Field(ge=0, le=1)
    company_event_risk: float = Field(ge=0, le=1)
    event_magnitude: float = Field(ge=0, le=1)
    dominant_category: EventCategory | None = None
    dominant_direction: EventDirection = EventDirection.UNKNOWN
    dominant_event_id: str | None = None


class MacroSurprise(DomainModel):
    """Surprise is computed only from provided actual/consensus. Never guessed."""

    series_id: str | None = None
    actual: Decimal | None = None
    consensus: Decimal | None = None
    previous: Decimal | None = None
    surprise: Decimal | None = None
    surprise_z_score: Decimal | None = None
    historical_std: Decimal | None = None
    missing_fields: list[str] = Field(default_factory=list)


class PricedInAnalysis(DomainModel):
    event_impact: float
    prior_price_movement: float | None = None
    post_event_reaction: float | None = None
    volume_reaction: float | None = None
    sector_reaction: float | None = None
    market_reaction: float | None = None
    already_priced_in: float | None = Field(default=None, ge=0, le=1)
    remaining_edge: float | None = Field(default=None, ge=0, le=1)
    method: str = "heuristic_v1"


class DivergenceSignal(DomainModel):
    code: ContextSignal
    event_direction: EventDirection
    market_reaction: float
    confidence_adjustment: float
    explanation: str


class MarketContext(DomainModel):
    """Feature snapshot for a later judgment step. Contains no Action/Decision."""

    ticker: str = Field(min_length=1)
    as_of: datetime
    regime: MarketRegime
    quantitative: QuantitativeFeatures
    event_features: EventImpactFeatures
    macro_surprise: MacroSurprise | None = None
    priced_in: PricedInAnalysis | None = None
    divergences: list[DivergenceSignal] = Field(default_factory=list)
    unknown_treated_as_safe: Literal[False] = False
    feature_version: str = CONTEXT_FEATURE_VERSION
    policy_version: str = POLICY_VERSION

    @property
    def regime_flags(self) -> list[MarketRegimeType]:
        return list(self.regime.flags)

    @property
    def regime_is_actionable(self) -> bool:
        return self.regime.treated_as_safe

    @model_validator(mode="after")
    def reject_trade_and_unknown_as_safe(self) -> MarketContext:
        dumped = self.model_dump()
        forbidden = {"action", "decision", "suggestedCapitalPct", "order"}
        if forbidden.intersection(dumped):
            raise ValueError("MarketContext must not carry trade fields")
        if self.unknown_treated_as_safe:
            raise ValueError("UNKNOWN must never be treated as safe")
        if self.regime.regime is MarketRegimeType.UNKNOWN and self.regime.treated_as_safe:
            raise ValueError("UNKNOWN regime is not safe")
        return self
