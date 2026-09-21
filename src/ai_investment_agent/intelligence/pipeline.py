from __future__ import annotations

from datetime import datetime, timezone

from ai_investment_agent.domain.enums import EventCategory, VerificationStatus
from ai_investment_agent.domain.event_intelligence import AnalyzedMarketEvent, RawEvent
from ai_investment_agent.domain.event_time import resolve_market_available_at
from ai_investment_agent.domain.ids import new_event_id
from ai_investment_agent.intelligence.dedup import EventDeduplicator
from ai_investment_agent.intelligence.entities import EntityExtractor
from ai_investment_agent.intelligence.impact import ImpactAnalyzer
from ai_investment_agent.intelligence.normalizer import EventNormalizer
from ai_investment_agent.intelligence.parser import EventParser
from ai_investment_agent.intelligence.sanitizer import EventSanitizer
from ai_investment_agent.intelligence.verification import EventVerifier
from ai_investment_agent.policy.source_trust import cluster_source_trust
from ai_investment_agent.ports.embeddings import EmbeddingProvider
from ai_investment_agent.ports.event_intelligence import IntelligenceEventStore


class EventIntelligenceEngine:
    """Raw Event → Parser → Sanitizer → Normalizer → Dedup → Entities → Trust → Verify → Impact.

    Terminal artifact is AnalyzedMarketEvent. No Action, Decision, or order is emitted.
    """

    def __init__(
        self,
        store: IntelligenceEventStore,
        embeddings: EmbeddingProvider | None = None,
        now_fn=None,
    ) -> None:
        self._store = store
        self._parser = EventParser()
        self._sanitizer = EventSanitizer()
        self._normalizer = EventNormalizer()
        self._deduper = EventDeduplicator(embeddings)
        self._extractor = EntityExtractor()
        self._verifier = EventVerifier()
        self._analyzer = ImpactAnalyzer()
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    def ingest(self, raw: RawEvent) -> AnalyzedMarketEvent:
        return self.ingest_many([raw])[0]

    def ingest_many(self, raws: list[RawEvent]) -> list[AnalyzedMarketEvent]:
        affected: list[str] = []
        for raw in raws:
            normalized = self._prepare(raw)
            cluster = self._deduper.add(normalized)
            existing = self._store.get_by_cluster(cluster.cluster_id)
            event = self._materialize(
                cluster.cluster_id,
                existing_id=existing.event_id if existing else None,
            )
            self._store.upsert(event)
            affected.append(cluster.cluster_id)
        return self._unique_events(affected)

    def retract(self, event_id: str, retraction: RawEvent) -> AnalyzedMarketEvent:
        current = self._store.get(event_id)
        if current is None:
            raise KeyError(f"unknown event {event_id}")
        normalized = self._prepare(retraction)
        self._deduper.attach(current.cluster_id, normalized)
        event = self._materialize(current.cluster_id, existing_id=current.event_id)
        if event.verification_status is not VerificationStatus.RETRACTED:
            event = event.model_copy(update={"verification_status": VerificationStatus.RETRACTED})
        self._store.upsert(event)
        return event

    def _prepare(self, raw: RawEvent):
        parsed = self._parser.parse(raw)
        sanitized = self._sanitizer.sanitize(parsed)
        return self._normalizer.normalize(sanitized, raw)

    def _unique_events(self, cluster_ids: list[str]) -> list[AnalyzedMarketEvent]:
        ordered: list[AnalyzedMarketEvent] = []
        seen: set[str] = set()
        for cluster_id in cluster_ids:
            event = self._store.get_by_cluster(cluster_id)
            if event is None or event.event_id in seen:
                continue
            ordered.append(event)
            seen.add(event.event_id)
        return ordered

    def _materialize(self, cluster_id: str, *, existing_id: str | None) -> AnalyzedMarketEvent:
        cluster = next(item for item in self._deduper.clusters() if item.cluster_id == cluster_id)
        members = self._deduper.members_of(cluster_id)
        entities = self._extractor.extract(members)
        category = entities.category or EventCategory.MARKET
        entities.category = category
        tier, trust = cluster_source_trust(cluster.member_sources)
        verification = self._verifier.verify(cluster, members)
        injection_blocked = any(member.injection_flags for member in members)
        impact = self._analyzer.analyze(
            members,
            entities,
            source_trust=trust,
            verification=verification,
            article_count=cluster.article_count,
            injection_blocked=injection_blocked,
        )
        published = [item.published_at for item in members if item.published_at is not None]
        collected = [item.collected_at for item in members if item.collected_at is not None]
        published_at = min(published) if published else None
        collected_at = min(collected) if collected else None
        market_available_at = resolve_market_available_at(
            published_at=published_at,
            collected_at=collected_at,
        )
        return AnalyzedMarketEvent(
            event_id=existing_id or new_event_id(),
            cluster_id=cluster.cluster_id,
            event_type=entities.event_type,
            category=category,
            countries=entities.countries,
            entities=entities.entities,
            sectors=entities.sectors,
            tickers=entities.tickers,
            direction=impact.direction,
            magnitude=impact.magnitude,
            source_trust=trust,
            novelty=impact.novelty,
            confidence=impact.confidence,
            verification_status=verification,
            impact_horizon=impact.impact_horizon,
            headline=cluster.canonical_headline,
            summary=impact.summary,
            article_count=cluster.article_count,
            source_ids=list(cluster.member_source_ids),
            member_raw_ids=list(cluster.member_raw_ids),
            source_tier=tier,
            injection_blocked=injection_blocked,
            published_at=published_at,
            collected_at=collected_at,
            market_available_at=market_available_at,
            analyzed_at=self._now(),
        )
