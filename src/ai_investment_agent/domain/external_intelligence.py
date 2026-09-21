from __future__ import annotations

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.collection import CollectionTimestamps
from ai_investment_agent.domain.enums import FreshnessClass, IntelligenceKind


class IntelligenceRecord(DomainModel):
    """External intelligence item. Never mixed with market-data quotes."""

    record_id: str = Field(min_length=1)
    kind: IntelligenceKind
    headline: str = Field(min_length=1)
    timestamps: CollectionTimestamps
    freshness_class: FreshnessClass
    ticker: str | None = None
    body: str | None = None
    source: str = "fixture"
    language: str | None = None
    country: str | None = None
    raw_ref: str | None = None
