from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import IntelligenceKind, MarketDataKind, RawPutResult
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord
from ai_investment_agent.domain.market_feed import MarketDataRecord
from ai_investment_agent.domain.raw import RawRecord


class MarketDataCollector(Protocol):
    """Collects quotes, bars, and related market observations only."""

    def collect(
        self,
        instrument: str,
        as_of: datetime,
        kinds: Sequence[MarketDataKind] | None = None,
    ) -> CollectionResult[MarketDataRecord]:
        """Return an explicit status. Failures are DATA_UNAVAILABLE, never empty OK."""
        ...


class NewsCollector(Protocol):
    """Domestic and foreign news only."""

    def collect(
        self,
        ticker: str | None,
        as_of: datetime,
        kinds: Sequence[IntelligenceKind] | None = None,
    ) -> CollectionResult[IntelligenceRecord]:
        ...


class DisclosureCollector(Protocol):
    """Corporate disclosures only."""

    def collect(self, ticker: str, as_of: datetime) -> CollectionResult[IntelligenceRecord]:
        ...


class MacroCollector(Protocol):
    """Central bank, government policy, economic indicators, geopolitics."""

    def collect(self, as_of: datetime) -> CollectionResult[IntelligenceRecord]:
        ...


class ScheduledEventCollector(Protocol):
    """Industry and corporate calendar events. Not corporate-action fixtures."""

    def collect(
        self,
        as_of: datetime,
        ticker: str | None = None,
    ) -> CollectionResult[IntelligenceRecord]:
        ...


class RawRecordStore(Protocol):
    def put(self, record: RawRecord) -> RawPutResult:
        ...

    def get(self, source: str, source_id: str) -> RawRecord | None:
        ...

    def get_by_checksum(self, checksum: str) -> RawRecord | None:
        ...
