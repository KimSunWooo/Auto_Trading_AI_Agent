from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass, IntelligenceKind, MarketDataKind

TItem = TypeVar("TItem")

FRESHNESS_MAX_AGE: dict[FreshnessClass, timedelta] = {
    FreshnessClass.ULTRA_FAST: timedelta(minutes=5),
    FreshnessClass.INTRADAY: timedelta(hours=4),
    FreshnessClass.DAILY: timedelta(hours=24),
    FreshnessClass.LONG_HORIZON: timedelta(days=30),
}

MARKET_DATA_FRESHNESS: dict[MarketDataKind, FreshnessClass] = {
    MarketDataKind.CURRENT_PRICE: FreshnessClass.ULTRA_FAST,
    MarketDataKind.VOLUME: FreshnessClass.ULTRA_FAST,
    MarketDataKind.INDEX: FreshnessClass.ULTRA_FAST,
    MarketDataKind.OHLCV: FreshnessClass.INTRADAY,
    MarketDataKind.FX: FreshnessClass.INTRADAY,
    MarketDataKind.COMMODITY: FreshnessClass.INTRADAY,
    MarketDataKind.VOLATILITY: FreshnessClass.INTRADAY,
    MarketDataKind.LIQUIDITY: FreshnessClass.INTRADAY,
    MarketDataKind.RATES: FreshnessClass.DAILY,
}

INTELLIGENCE_FRESHNESS: dict[IntelligenceKind, FreshnessClass] = {
    IntelligenceKind.DOMESTIC_NEWS: FreshnessClass.INTRADAY,
    IntelligenceKind.FOREIGN_NEWS: FreshnessClass.INTRADAY,
    IntelligenceKind.CORPORATE_DISCLOSURE: FreshnessClass.DAILY,
    IntelligenceKind.ECONOMIC_INDICATOR: FreshnessClass.DAILY,
    IntelligenceKind.INDUSTRY_EVENT: FreshnessClass.LONG_HORIZON,
    IntelligenceKind.CORPORATE_EVENT: FreshnessClass.LONG_HORIZON,
    IntelligenceKind.CENTRAL_BANK: FreshnessClass.LONG_HORIZON,
    IntelligenceKind.GOVERNMENT_POLICY: FreshnessClass.LONG_HORIZON,
    IntelligenceKind.GEOPOLITICS: FreshnessClass.LONG_HORIZON,
}


def _require_aware(name: str, value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


class CollectionTimestamps(DomainModel):
    """Integrity timestamps for collected records.

    Replay/backtest may use a record only when tradableAt and
    sourceReceivedAt (when present) are <= as_of.
    """

    event_occurred_at: datetime | None = None
    published_at: datetime | None = None
    source_received_at: datetime | None = None
    collected_at: datetime
    normalized_at: datetime | None = None
    analyzed_at: datetime | None = None
    tradable_at: datetime

    @model_validator(mode="after")
    def check_integrity(self) -> CollectionTimestamps:
        # eventOccurredAt is independent: a filing can describe a past event, and a
        # calendar item can be published before the event occurs.
        if self.event_occurred_at is not None:
            _require_aware("eventOccurredAt", self.event_occurred_at)

        pipeline = [
            ("publishedAt", self.published_at),
            ("sourceReceivedAt", self.source_received_at),
            ("collectedAt", self.collected_at),
            ("normalizedAt", self.normalized_at),
            ("analyzedAt", self.analyzed_at),
        ]
        last_name = None
        last_value: datetime | None = None
        for name, value in pipeline:
            if value is None:
                continue
            _require_aware(name, value)
            if last_value is not None and value < last_value:
                raise ValueError(f"{name} must not precede {last_name}")
            last_name, last_value = name, value

        _require_aware("tradableAt", self.tradable_at)
        if self.source_received_at is not None and self.tradable_at < self.source_received_at:
            raise ValueError("tradableAt must not precede sourceReceivedAt")
        if self.published_at is not None and self.tradable_at < self.published_at:
            raise ValueError("tradableAt must not precede publishedAt")
        return self


class CollectionResult(DomainModel, Generic[TItem]):
    """Collector return value. Status is mandatory; empty lists are not success."""

    status: CollectionStatus
    items: list[TItem] = Field(default_factory=list)
    error: str | None = None
    as_of: datetime
    freshness_class: FreshnessClass | None = None
    stale_item_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_status_contract(self) -> CollectionResult[TItem]:
        _require_aware("asOf", self.as_of)
        if self.status is CollectionStatus.OK:
            if not self.items:
                raise ValueError(
                    "OK must not use an empty item list; that would hide NO_EVENT or DATA_UNAVAILABLE"
                )
            if self.error is not None:
                raise ValueError("OK must not carry an error; use DATA_UNAVAILABLE")
        elif self.status is CollectionStatus.NO_EVENT:
            if self.items:
                raise ValueError("NO_EVENT means the collector succeeded and found no events")
            if self.error is not None:
                raise ValueError("NO_EVENT must not carry an error; that is DATA_UNAVAILABLE")
        elif self.status is CollectionStatus.DATA_UNAVAILABLE:
            if not self.error:
                raise ValueError("DATA_UNAVAILABLE requires an error description")
            if self.items:
                raise ValueError(
                    "DATA_UNAVAILABLE must not return items; a failed fetch is not a successful empty feed"
                )
        elif self.status is CollectionStatus.STALE:
            if not self.items:
                raise ValueError("STALE requires the stale items; an empty failure is DATA_UNAVAILABLE")
            if self.error is not None:
                raise ValueError("STALE is a freshness judgment, not a collector failure")
        return self

    @property
    def failed(self) -> bool:
        return self.status is CollectionStatus.DATA_UNAVAILABLE

    @property
    def is_no_event(self) -> bool:
        return self.status is CollectionStatus.NO_EVENT

    @classmethod
    def ok(
        cls,
        items: list[TItem],
        *,
        as_of: datetime,
        freshness_class: FreshnessClass | None = None,
        stale_item_ids: list[str] | None = None,
    ) -> CollectionResult[TItem]:
        return cls(
            status=CollectionStatus.OK,
            items=items,
            as_of=as_of,
            freshness_class=freshness_class,
            stale_item_ids=stale_item_ids or [],
        )

    @classmethod
    def no_event(
        cls,
        *,
        as_of: datetime,
        freshness_class: FreshnessClass | None = None,
    ) -> CollectionResult[Any]:
        return cls(
            status=CollectionStatus.NO_EVENT,
            items=[],
            as_of=as_of,
            freshness_class=freshness_class,
        )

    @classmethod
    def unavailable(
        cls,
        *,
        error: str,
        as_of: datetime,
        freshness_class: FreshnessClass | None = None,
    ) -> CollectionResult[Any]:
        return cls(
            status=CollectionStatus.DATA_UNAVAILABLE,
            items=[],
            error=error,
            as_of=as_of,
            freshness_class=freshness_class,
        )

    @classmethod
    def stale(
        cls,
        items: list[TItem],
        *,
        as_of: datetime,
        freshness_class: FreshnessClass | None = None,
        stale_item_ids: list[str] | None = None,
    ) -> CollectionResult[TItem]:
        ids = stale_item_ids if stale_item_ids is not None else []
        return cls(
            status=CollectionStatus.STALE,
            items=items,
            as_of=as_of,
            freshness_class=freshness_class,
            stale_item_ids=ids,
        )


def is_accessible_at(timestamps: CollectionTimestamps, as_of: datetime) -> bool:
    """True when the record was actually usable at as_of (no look-ahead)."""
    _require_aware("asOf", as_of)
    if timestamps.tradable_at > as_of:
        return False
    if timestamps.source_received_at is not None and timestamps.source_received_at > as_of:
        return False
    return True


def availability_time(timestamps: CollectionTimestamps) -> datetime:
    if timestamps.source_received_at is not None:
        return timestamps.source_received_at
    return timestamps.tradable_at


def is_stale(
    timestamps: CollectionTimestamps,
    as_of: datetime,
    freshness_class: FreshnessClass,
) -> bool:
    """Stale only applies to data that was already accessible. Future data is look-ahead, not stale."""
    if not is_accessible_at(timestamps, as_of):
        return False
    age = as_of - availability_time(timestamps)
    return age > FRESHNESS_MAX_AGE[freshness_class]
