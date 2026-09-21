from __future__ import annotations

from collections.abc import Sequence

from ai_investment_agent.domain.event_intelligence import AnalyzedMarketEvent
from ai_investment_agent.domain.errors import DomainError


class EventStoreDeleteError(DomainError):
    pass


class InMemoryIntelligenceEventStore:
    def __init__(self) -> None:
        self._by_id: dict[str, AnalyzedMarketEvent] = {}
        self._by_cluster: dict[str, AnalyzedMarketEvent] = {}

    def upsert(self, event: AnalyzedMarketEvent) -> None:
        self._by_id[event.event_id] = event
        self._by_cluster[event.cluster_id] = event

    def get(self, event_id: str) -> AnalyzedMarketEvent | None:
        return self._by_id.get(event_id)

    def get_by_cluster(self, cluster_id: str) -> AnalyzedMarketEvent | None:
        return self._by_cluster.get(cluster_id)

    def list_all(self) -> Sequence[AnalyzedMarketEvent]:
        return tuple(self._by_id.values())

    def delete(self, event_id: str) -> None:
        raise EventStoreDeleteError(
            "Analyzed events are not deleted. Mark verificationStatus=RETRACTED."
        )

    def __len__(self) -> int:
        return len(self._by_id)
