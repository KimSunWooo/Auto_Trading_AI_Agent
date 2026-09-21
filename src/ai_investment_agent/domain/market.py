from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import EventSeverity, MarketRegimeType


class MarketSnapshot(DomainModel):
    ticker: str = Field(min_length=1)
    as_of: datetime
    last_price: Decimal | None = None
    currency: str = "KRW"
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    volume: Decimal | None = Field(default=None, ge=0)
    volatility: Decimal | None = Field(default=None, ge=0)
    liquidity_score: Decimal | None = Field(default=None, ge=0, le=1)
    data_completeness: Decimal = Field(ge=0, le=1)
    regime_hint: MarketRegimeType | None = None
    source: str = "fixture"


class MarketEvent(DomainModel):
    event_id: str = Field(min_length=1)
    ticker: str | None = None
    event_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    occurred_at: datetime
    severity: EventSeverity = EventSeverity.INFO
    source: str = "fixture"
    payload: dict[str, Any] = Field(default_factory=dict)


class MarketRegime(DomainModel):
    regime: MarketRegimeType
    confidence: float = Field(ge=0, le=1)
    as_of: datetime
    explanation: str
    detected_from: str = "fixture"
