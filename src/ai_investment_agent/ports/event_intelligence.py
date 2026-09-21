from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ai_investment_agent.domain.event_intelligence import AnalyzedMarketEvent


class IntelligenceEventStore(Protocol):
    """Persists analyzed events. Retraction updates status; it does not delete."""

    def upsert(self, event: AnalyzedMarketEvent) -> None:
        ...

    def get(self, event_id: str) -> AnalyzedMarketEvent | None:
        ...

    def get_by_cluster(self, cluster_id: str) -> AnalyzedMarketEvent | None:
        ...

    def list_all(self) -> Sequence[AnalyzedMarketEvent]:
        ...
