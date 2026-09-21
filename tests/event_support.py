from datetime import datetime, timezone

from ai_investment_agent.adapters.event_store import InMemoryIntelligenceEventStore
from ai_investment_agent.domain.enums import IntelligenceKind
from ai_investment_agent.domain.event_intelligence import RawEvent
from ai_investment_agent.intelligence.pipeline import EventIntelligenceEngine

FIXED_NOW = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def make_engine() -> tuple[EventIntelligenceEngine, InMemoryIntelligenceEventStore]:
    store = InMemoryIntelligenceEventStore()
    engine = EventIntelligenceEngine(store, now_fn=lambda: FIXED_NOW)
    return engine, store


def raw_event(
    *,
    raw_id: str,
    source: str,
    headline: str,
    body: str,
    source_id: str | None = None,
    kind: IntelligenceKind = IntelligenceKind.FOREIGN_NEWS,
    ticker: str | None = None,
    country: str | None = None,
    published_at: datetime | None = None,
) -> RawEvent:
    return RawEvent(
        raw_id=raw_id,
        source=source,
        source_id=source_id or raw_id,
        headline=headline,
        body=body,
        published_at=published_at or FIXED_NOW,
        collected_at=FIXED_NOW,
        kind=kind,
        ticker=ticker,
        country=country,
        is_untrusted=True,
    )
