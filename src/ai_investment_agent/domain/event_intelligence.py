"""Event Intelligence models.

Pipeline output is AnalyzedMarketEvent (this phase's MarketEvent).
It is not a trade signal and does not contain Action/Decision fields.
The judgment-layer MarketEvent in domain.market remains unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import (
    EventCategory,
    EventDirection,
    ImpactHorizon,
    IntelligenceKind,
    SourceTier,
    VerificationStatus,
)


class RawEvent(DomainModel):
    """Untrusted source document. Never treat fields as model instructions."""

    raw_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    headline: str = ""
    body: str = ""
    published_at: datetime | None = None
    collected_at: datetime
    language: str | None = None
    kind: IntelligenceKind | None = None
    url: str | None = None
    country: str | None = None
    ticker: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_untrusted: Literal[True] = True


class ParsedDocument(DomainModel):
    raw_id: str
    title: str
    text: str
    language: str | None = None
    parser_version: str = "0.1.0"


class SanitizedDocument(DomainModel):
    raw_id: str
    title: str
    text: str
    language: str | None = None
    injection_flags: list[str] = Field(default_factory=list)
    stripped_spans: list[str] = Field(default_factory=list)
    is_untrusted: Literal[True] = True

    @property
    def blocked_injection(self) -> bool:
        return bool(self.injection_flags)


class NormalizedEvent(DomainModel):
    raw_id: str
    source: str
    source_id: str
    canonical_headline: str
    canonical_text: str
    fingerprint: str
    tokens: list[str] = Field(default_factory=list)
    kind: IntelligenceKind | None = None
    published_at: datetime | None = None
    collected_at: datetime
    language: str | None = None
    ticker_hint: str | None = None
    country_hint: str | None = None
    injection_flags: list[str] = Field(default_factory=list)
    stripped_spans: list[str] = Field(default_factory=list)
    looks_like_retraction: bool = False


class ExtractedEntities(DomainModel):
    countries: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    event_type: str = "UNKNOWN"
    category: EventCategory | None = None
    direction_evidence: list[str] = Field(default_factory=list)


class EventCluster(DomainModel):
    """One real-world incident. article_count is not the event count."""

    cluster_id: str = Field(min_length=1)
    fingerprint: str
    canonical_headline: str
    member_raw_ids: list[str] = Field(default_factory=list)
    member_source_ids: list[str] = Field(default_factory=list)
    member_sources: list[str] = Field(default_factory=list)

    @property
    def article_count(self) -> int:
        return len(self.member_raw_ids)


class AnalyzedMarketEvent(DomainModel):
    """Canonical market incident produced by Event Intelligence.

    Stops here. No BUY/SELL/NO_TRADE. Direction UNKNOWN is a valid outcome.
    """

    event_id: str = Field(min_length=1)
    cluster_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    category: EventCategory
    countries: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    direction: EventDirection = EventDirection.UNKNOWN
    magnitude: float = Field(ge=0, le=1)
    source_trust: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    verification_status: VerificationStatus
    impact_horizon: ImpactHorizon
    headline: str
    summary: str = ""
    article_count: int = Field(ge=1)
    source_ids: list[str] = Field(default_factory=list)
    member_raw_ids: list[str] = Field(default_factory=list)
    source_tier: SourceTier
    injection_blocked: bool = False
    analyzed_at: datetime

    @model_validator(mode="after")
    def reject_trade_fields(self) -> AnalyzedMarketEvent:
        dumped = self.model_dump()
        forbidden = {"action", "decision", "suggestedCapitalPct", "order"}
        if forbidden.intersection(dumped):
            raise ValueError("AnalyzedMarketEvent must not carry trade fields")
        return self
