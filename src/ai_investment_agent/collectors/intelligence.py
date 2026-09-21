from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from ai_investment_agent.collectors.loading import DATA_DIR, intelligence_record_from_dict
from ai_investment_agent.collectors.query import collect_accessible
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, IntelligenceKind
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord

NEWS_KINDS = frozenset({IntelligenceKind.DOMESTIC_NEWS, IntelligenceKind.FOREIGN_NEWS})
DISCLOSURE_KINDS = frozenset({IntelligenceKind.CORPORATE_DISCLOSURE})
MACRO_KINDS = frozenset(
    {
        IntelligenceKind.CENTRAL_BANK,
        IntelligenceKind.GOVERNMENT_POLICY,
        IntelligenceKind.ECONOMIC_INDICATOR,
        IntelligenceKind.GEOPOLITICS,
    }
)
SCHEDULED_KINDS = frozenset(
    {IntelligenceKind.INDUSTRY_EVENT, IntelligenceKind.CORPORATE_EVENT}
)


def load_intelligence_records(name: str = "intelligence.json") -> list[IntelligenceRecord]:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return [intelligence_record_from_dict(item) for item in raw.get("records", [])]


class _FixtureIntelligenceCollector:
    allowed_kinds: frozenset[IntelligenceKind]
    unavailable_reason: str = "fixture intelligence API failure"

    def __init__(
        self,
        records: Sequence[IntelligenceRecord] | None = None,
        *,
        unavailable: bool = False,
        unavailable_reason: str | None = None,
    ) -> None:
        incoming = list(records or [])
        self._records = [record for record in incoming if record.kind in self.allowed_kinds]
        self._unavailable = unavailable
        if unavailable_reason is not None:
            self.unavailable_reason = unavailable_reason

    @classmethod
    def from_file(cls, name: str = "intelligence.json") -> _FixtureIntelligenceCollector:
        return cls(load_intelligence_records(name))

    @classmethod
    def from_path(cls, path: Path) -> _FixtureIntelligenceCollector:
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        return cls([intelligence_record_from_dict(item) for item in raw.get("records", [])])

    def _collect(
        self,
        as_of: datetime,
        *,
        ticker: str | None = None,
        kinds: Sequence[IntelligenceKind] | None = None,
        match_global_when_ticker_set: bool = True,
    ) -> CollectionResult[IntelligenceRecord]:
        requested = set(kinds) if kinds is not None else set(self.allowed_kinds)
        if not requested.issubset(self.allowed_kinds):
            invalid = requested - self.allowed_kinds
            return CollectionResult.unavailable(
                error=f"Collector does not serve kinds: {sorted(k.value for k in invalid)}",
                as_of=as_of,
            )

        def match(record: IntelligenceRecord) -> bool:
            if record.kind not in requested:
                return False
            if ticker is None:
                return True
            if record.ticker == ticker:
                return True
            return match_global_when_ticker_set and record.ticker is None

        return collect_accessible(
            self._records,
            as_of=as_of,
            unavailable=self._unavailable,
            unavailable_reason=self.unavailable_reason,
            match=match,
            timestamps_of=lambda record: record.timestamps,
            freshness_of=lambda record: record.freshness_class,
            id_of=lambda record: record.record_id,
            empty_status=CollectionStatus.NO_EVENT,
        )


class FixtureNewsCollector(_FixtureIntelligenceCollector):
    allowed_kinds = NEWS_KINDS
    unavailable_reason = "fixture news API failure"

    def collect(
        self,
        ticker: str | None,
        as_of: datetime,
        kinds: Sequence[IntelligenceKind] | None = None,
    ) -> CollectionResult[IntelligenceRecord]:
        return self._collect(as_of, ticker=ticker, kinds=kinds)


class FixtureDisclosureCollector(_FixtureIntelligenceCollector):
    allowed_kinds = DISCLOSURE_KINDS
    unavailable_reason = "fixture disclosure API failure"

    def collect(self, ticker: str, as_of: datetime) -> CollectionResult[IntelligenceRecord]:
        return self._collect(as_of, ticker=ticker, match_global_when_ticker_set=False)


class FixtureMacroCollector(_FixtureIntelligenceCollector):
    allowed_kinds = MACRO_KINDS
    unavailable_reason = "fixture macro API failure"

    def collect(self, as_of: datetime) -> CollectionResult[IntelligenceRecord]:
        return self._collect(as_of, ticker=None)


class FixtureScheduledEventCollector(_FixtureIntelligenceCollector):
    allowed_kinds = SCHEDULED_KINDS
    unavailable_reason = "fixture scheduled-event API failure"

    def collect(
        self,
        as_of: datetime,
        ticker: str | None = None,
    ) -> CollectionResult[IntelligenceRecord]:
        return self._collect(as_of, ticker=ticker)
