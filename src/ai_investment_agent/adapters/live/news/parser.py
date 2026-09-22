"""Parse news JSON into IntelligenceRecord. Body is untrusted."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_investment_agent.collectors.loading import parse_dt
from ai_investment_agent.domain.collection import (
    INTELLIGENCE_FRESHNESS,
    CollectionTimestamps,
)
from ai_investment_agent.domain.enums import IntelligenceKind
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord

SOURCE = "live-news"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _kind(item: dict[str, Any]) -> IntelligenceKind:
    raw = str(item.get("kind") or item.get("scope") or "").upper()
    country = str(item.get("country") or item.get("language") or "").upper()
    if raw in {"FOREIGN_NEWS", "GLOBAL", "FOREIGN"}:
        return IntelligenceKind.FOREIGN_NEWS
    if raw in {"DOMESTIC_NEWS", "DOMESTIC", "KR"}:
        return IntelligenceKind.DOMESTIC_NEWS
    if country in {"KR", "KO", "KOR"}:
        return IntelligenceKind.DOMESTIC_NEWS
    return IntelligenceKind.FOREIGN_NEWS


def parse_news_payload(
    payload: dict[str, Any],
    *,
    ticker: str | None,
    collected_at: datetime,
) -> list[IntelligenceRecord]:
    collected = _aware(collected_at)
    items = payload.get("articles") or payload.get("items") or payload.get("list") or []
    if not isinstance(items, list):
        raise ValueError("news items must be a list")

    records: list[IntelligenceRecord] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        headline = str(item.get("headline") or item.get("title") or "").strip()
        if not headline:
            continue
        # Retraction / correction markers are preserved for Event Intelligence.
        body = str(item.get("body") or item.get("description") or item.get("content") or "")
        if item.get("retracted") or item.get("is_retraction"):
            body = f"[RETRACTION] {body}".strip()
        if item.get("correction") or item.get("is_correction"):
            body = f"[CORRECTION] {body}".strip()
        kind = _kind(item)
        published = (
            parse_dt(item.get("publishedAt") or item.get("published_at") or item.get("pubDate"))
            or collected
        )
        received = parse_dt(item.get("sourceReceivedAt") or item.get("source_received_at"))
        if received is None:
            received = published
        if received < published:
            received = published
        collected_ts = collected if collected >= received else received
        ts = CollectionTimestamps(
            event_occurred_at=parse_dt(item.get("eventOccurredAt")) or published,
            published_at=published,
            source_received_at=received,
            collected_at=collected_ts,
            normalized_at=collected_ts,
            tradable_at=received,
        )
        source_id = str(item.get("id") or item.get("url") or f"news_{index}")
        item_ticker = item.get("ticker")
        if item_ticker is None and ticker is not None:
            item_ticker = ticker
        records.append(
            IntelligenceRecord(
                record_id=f"news_{abs(hash(source_id)) % (10**12)}",
                kind=kind,
                headline=headline,
                timestamps=ts,
                freshness_class=INTELLIGENCE_FRESHNESS[kind],
                ticker=str(item_ticker) if item_ticker else None,
                body=body or None,
                source=str(item.get("source") or SOURCE),
                language=item.get("language"),
                country=item.get("country"),
                raw_ref=source_id[:200],
            )
        )
    return records
