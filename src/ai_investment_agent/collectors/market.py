from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from ai_investment_agent.collectors.loading import DATA_DIR, market_record_from_dict
from ai_investment_agent.collectors.query import collect_accessible
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, MarketDataKind
from ai_investment_agent.domain.market_feed import MarketDataRecord


def _load_records(name: str) -> list[MarketDataRecord]:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return [market_record_from_dict(item) for item in raw.get("records", [])]


class FixtureMarketDataCollector:
    """Fixture-only market data collector. Never returns news or filings."""

    def __init__(
        self,
        records: Sequence[MarketDataRecord] | None = None,
        *,
        unavailable: bool = False,
        unavailable_reason: str = "fixture market data API failure",
    ) -> None:
        self._records = list(records or [])
        self._unavailable = unavailable
        self._unavailable_reason = unavailable_reason

    @classmethod
    def from_file(cls, name: str = "market_data.json") -> FixtureMarketDataCollector:
        return cls(_load_records(name))

    @classmethod
    def from_path(cls, path: Path) -> FixtureMarketDataCollector:
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        return cls([market_record_from_dict(item) for item in raw.get("records", [])])

    def collect(
        self,
        instrument: str,
        as_of: datetime,
        kinds: Sequence[MarketDataKind] | None = None,
    ) -> CollectionResult[MarketDataRecord]:
        allowed = set(kinds) if kinds is not None else None

        def match(record: MarketDataRecord) -> bool:
            if record.instrument != instrument:
                return False
            if allowed is not None and record.kind not in allowed:
                return False
            return True

        return collect_accessible(
            self._records,
            as_of=as_of,
            unavailable=self._unavailable,
            unavailable_reason=self._unavailable_reason,
            match=match,
            timestamps_of=lambda record: record.timestamps,
            freshness_of=lambda record: record.freshness_class,
            id_of=lambda record: record.record_id,
            empty_status=CollectionStatus.DATA_UNAVAILABLE,
            empty_error=f"No accessible market data for {instrument} at {as_of.isoformat()}",
        )
