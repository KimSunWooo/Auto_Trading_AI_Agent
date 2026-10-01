"""Parse news JSON into IntelligenceRecord. Body is untrusted."""

from __future__ import annotations

import hashlib
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


def stable_news_record_id(source_id: str, *, source: str = SOURCE) -> str:
    material = f"{source}\0{source_id}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"news_{digest}"


def parse_news_payload(
    payload: dict[str, Any],
    *,
    ticker: str | None,
    collected_at: datetime,
) -> list[IntelligenceRecord]:
    collected = _aware(collected_at)
    if not any(key in payload for key in ("articles", "items", "list")):
        raise ValueError("news payload missing articles")
    items = payload.get("articles")
    if items is None:
        items = payload.get("items")
    if items is None:
        items = payload.get("list")
    if items is None:
        items = []
    if not isinstance(items, list):
        raise TypeError("news items must be a list")
    if not items:
        return []

    records: list[IntelligenceRecord] = []
    skipped_incomplete = 0
    for item in items:
        if not isinstance(item, dict):
            skipped_incomplete += 1
            continue
        headline = str(item.get("headline") or item.get("title") or "").strip()
        if not headline:
            skipped_incomplete += 1
            continue
        published = parse_dt(item.get("publishedAt") or item.get("published_at") or item.get("pubDate"))
        if published is None:
            skipped_incomplete += 1
            continue
        body = str(item.get("body") or item.get("description") or item.get("content") or "")
        related = item.get("relatedId") or item.get("replaces") or item.get("originalId")
        if item.get("retracted") or item.get("is_retraction"):
            body = f"[RETRACTION] {body}".strip()
        if item.get("correction") or item.get("is_correction"):
            body = f"[CORRECTION] {body}".strip()
        if related:
            body = f"{body} [RELATED:{related}]".strip()
        kind = _kind(item)
        received = parse_dt(item.get("sourceReceivedAt") or item.get("source_received_at"))
        if received is None:
            received = collected
        if received < published:
            received = published
        collected_ts = collected if collected >= received else received
        tradable = received if received >= published else published
        ts = CollectionTimestamps(
            event_occurred_at=parse_dt(item.get("eventOccurredAt")) or published,
            published_at=published,
            source_received_at=received,
            collected_at=collected_ts,
            normalized_at=collected_ts,
            tradable_at=tradable,
        )
        source_id = str(item.get("id") or item.get("url") or "").strip()
        item_source = str(item.get("source") or SOURCE)
        if not source_id:
            published_key = str(
                item.get("publishedAt") or item.get("published_at") or item.get("pubDate") or ""
            )
            source_id = "|".join(
                [headline, published_key, str(item.get("ticker") or ticker or "")]
            )
        item_ticker = item.get("ticker")
        if item_ticker is None and ticker is not None:
            item_ticker = ticker
        records.append(
            IntelligenceRecord(
                record_id=stable_news_record_id(source_id, source=item_source),
                kind=kind,
                headline=headline,
                timestamps=ts,
                freshness_class=INTELLIGENCE_FRESHNESS[kind],
                ticker=str(item_ticker) if item_ticker else None,
                body=body or None,
                source=str(item.get("source") or SOURCE),
                language=item.get("language"),
                country=item.get("country"),
                raw_ref=str(related or source_id)[:200],
            )
        )
    if not records and skipped_incomplete:
        raise ValueError("news payload had items but none contained required fields")
    return records
