from __future__ import annotations

from datetime import date

from ai_investment_agent.adapters.fixtures.embeddings import HashedBagEmbeddingProvider
from ai_investment_agent.domain.event_intelligence import EventCluster, NormalizedEvent
from ai_investment_agent.domain.ids import new_cluster_id
from ai_investment_agent.intelligence.text import cosine, jaccard
from ai_investment_agent.ports.embeddings import EmbeddingProvider

_JACCARD_THRESHOLD = 0.42
_COSINE_THRESHOLD = 0.82


class EventDeduplicator:
    """Groups articles into incident clusters. Article count is not event count."""

    def __init__(self, embeddings: EmbeddingProvider | None = None) -> None:
        self._embeddings = embeddings or HashedBagEmbeddingProvider()
        self._clusters: list[EventCluster] = []
        self._members: dict[str, list[NormalizedEvent]] = {}

    def reset(self) -> None:
        self._clusters.clear()
        self._members.clear()

    def add(self, normalized: NormalizedEvent) -> EventCluster:
        match = self._find(normalized)
        if match is None:
            cluster = EventCluster(
                cluster_id=new_cluster_id(),
                fingerprint=normalized.fingerprint,
                canonical_headline=normalized.canonical_headline,
                member_raw_ids=[normalized.raw_id],
                member_source_ids=[normalized.source_id],
                member_sources=[normalized.source],
            )
            self._clusters.append(cluster)
            self._members[cluster.cluster_id] = [normalized]
            return cluster

        if normalized.raw_id not in match.member_raw_ids:
            match.member_raw_ids.append(normalized.raw_id)
            match.member_source_ids.append(normalized.source_id)
            match.member_sources.append(normalized.source)
            self._members[match.cluster_id].append(normalized)
        return match

    def attach(self, cluster_id: str, normalized: NormalizedEvent) -> EventCluster:
        cluster = next(item for item in self._clusters if item.cluster_id == cluster_id)
        if normalized.raw_id not in cluster.member_raw_ids:
            cluster.member_raw_ids.append(normalized.raw_id)
            cluster.member_source_ids.append(normalized.source_id)
            cluster.member_sources.append(normalized.source)
            self._members[cluster.cluster_id].append(normalized)
        return cluster

    def members_of(self, cluster_id: str) -> list[NormalizedEvent]:
        return list(self._members.get(cluster_id, ()))

    def clusters(self) -> list[EventCluster]:
        return list(self._clusters)

    def _find(self, normalized: NormalizedEvent) -> EventCluster | None:
        incoming_day = _day(normalized)
        for cluster in self._clusters:
            members = self._members[cluster.cluster_id]
            prototype = members[0]
            if incoming_day != _day(prototype):
                continue
            if normalized.fingerprint == prototype.fingerprint:
                return cluster
            if normalized.ticker_hint and prototype.ticker_hint:
                if normalized.ticker_hint != prototype.ticker_hint:
                    continue
            if jaccard(normalized.tokens, prototype.tokens) >= _JACCARD_THRESHOLD:
                return cluster
            left, right = self._embeddings.embed(
                [normalized.canonical_text, prototype.canonical_text]
            )
            if cosine(left, right) >= _COSINE_THRESHOLD:
                return cluster
        return None


def _day(normalized: NormalizedEvent) -> date | None:
    stamp = normalized.published_at or normalized.collected_at
    return stamp.date()
