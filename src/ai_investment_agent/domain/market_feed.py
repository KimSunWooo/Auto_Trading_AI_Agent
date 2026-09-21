from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.collection import CollectionTimestamps
from ai_investment_agent.domain.enums import FreshnessClass, MarketDataKind


class OhlcvBar(DomainModel):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Field(ge=0)
    bar_start: datetime
    bar_end: datetime

    @model_validator(mode="after")
    def check_range(self) -> OhlcvBar:
        if self.bar_end < self.bar_start:
            raise ValueError("barEnd must not precede barStart")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        return self


class MarketDataRecord(DomainModel):
    """Collection-layer market observation. Separate from judgment MarketSnapshot."""

    record_id: str = Field(min_length=1)
    kind: MarketDataKind
    instrument: str = Field(min_length=1)
    timestamps: CollectionTimestamps
    freshness_class: FreshnessClass
    value: Decimal | None = None
    ohlcv: OhlcvBar | None = None
    currency: str | None = None
    unit: str | None = None
    source: str = "fixture"
    raw_ref: str | None = None

    @model_validator(mode="after")
    def check_payload(self) -> MarketDataRecord:
        if self.kind is MarketDataKind.OHLCV:
            if self.ohlcv is None:
                raise ValueError("OHLCV records require an ohlcv bar")
        elif self.value is None:
            raise ValueError(f"{self.kind.value} records require a value")
        return self
