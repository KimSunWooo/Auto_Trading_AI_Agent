from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import EventSeverity, MarketRegimeType

UNSAFE_KNOWN_REGIMES = {
    MarketRegimeType.CRISIS,
    MarketRegimeType.EVENT_RISK,
    MarketRegimeType.LOW_LIQUIDITY,
    MarketRegimeType.HIGH_VOLATILITY,
}


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
    flags: list[MarketRegimeType] = Field(default_factory=list)

    @property
    def is_unknown(self) -> bool:
        return self.regime is MarketRegimeType.UNKNOWN

    @property
    def is_known(self) -> bool:
        return self.regime is not MarketRegimeType.UNKNOWN

    @property
    def treated_as_safe(self) -> bool:
        """Known is not the same as safe. CRISIS/EVENT_RISK stay unsafe."""
        return self.is_known and self.regime not in UNSAFE_KNOWN_REGIMES
