"""Parse official macro / economic JSON into IntelligenceRecord values.

Consensus is never invented — missing consensus stays None in downstream features.
"""

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

SOURCE = "live-macro"

KIND_MAP = {
    "CENTRAL_BANK": IntelligenceKind.CENTRAL_BANK,
    "GOVERNMENT_POLICY": IntelligenceKind.GOVERNMENT_POLICY,
    "ECONOMIC_INDICATOR": IntelligenceKind.ECONOMIC_INDICATOR,
    "GEOPOLITICS": IntelligenceKind.GEOPOLITICS,
    "RATE_DECISION": IntelligenceKind.CENTRAL_BANK,
    "CPI": IntelligenceKind.ECONOMIC_INDICATOR,
    "GDP": IntelligenceKind.ECONOMIC_INDICATOR,
    "EMPLOYMENT": IntelligenceKind.ECONOMIC_INDICATOR,
}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_macro_payload(
    payload: dict[str, Any],
    *,
    collected_at: datetime,
) -> list[IntelligenceRecord]:
    collected = _aware(collected_at)
    has_list = any(key in payload for key in ("items", "observations", "list"))
    items = payload.get("items")
    if items is None:
        items = payload.get("observations")
    if items is None:
        items = payload.get("list")
    if isinstance(payload.get("headline"), str) and not has_list:
        items = [payload]
        has_list = True
    if not has_list and items is None:
        raise ValueError("macro payload missing items")
    if items is None:
        items = []
    if not isinstance(items, list):
        raise TypeError("macro items must be a list")
    if not items:
        return []

    records: list[IntelligenceRecord] = []
    skipped_incomplete = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            skipped_incomplete += 1
            continue
        headline = str(item.get("headline") or item.get("title") or item.get("series_id") or "").strip()
        if not headline:
            skipped_incomplete += 1
            continue
        published = parse_dt(
            item.get("publishedAt") or item.get("published_at") or item.get("date")
        )
        if published is None:
            skipped_incomplete += 1
            continue
        kind_raw = str(item.get("kind") or item.get("category") or "ECONOMIC_INDICATOR").upper()
        kind = KIND_MAP.get(kind_raw, IntelligenceKind.ECONOMIC_INDICATOR)
        received = parse_dt(item.get("sourceReceivedAt") or item.get("source_received_at"))
        if received is None:
            received = collected
        if received < published:
            received = published
        collected_ts = collected if collected >= received else received
        tradable = received if received >= published else published
        ts = CollectionTimestamps(
            event_occurred_at=parse_dt(item.get("eventOccurredAt") or item.get("event_occurred_at"))
            or published,
            published_at=published,
            source_received_at=received,
            collected_at=collected_ts,
            normalized_at=collected_ts,
            tradable_at=tradable,
        )
        actual = item.get("actual")
        consensus = item.get("consensus")
        previous = item.get("previous")
        body_bits = []
        if actual is not None:
            body_bits.append(f"actual={actual}")
        if consensus is not None:
            body_bits.append(f"consensus={consensus}")
        else:
            body_bits.append("consensus=None")
        if previous is not None:
            body_bits.append(f"previous={previous}")
        if item.get("body"):
            body_bits.append(str(item["body"]))
        source_id = str(item.get("id") or item.get("series_id") or f"macro_{index}")
        records.append(
            IntelligenceRecord(
                record_id=f"macro_{source_id}",
                kind=kind,
                headline=headline,
                timestamps=ts,
                freshness_class=INTELLIGENCE_FRESHNESS[kind],
                ticker=None,
                body="; ".join(body_bits) if body_bits else None,
                source=str(item.get("source") or SOURCE),
                language=item.get("language"),
                country=item.get("country"),
                raw_ref=source_id,
            )
        )
    if not records and skipped_incomplete:
        raise ValueError("macro payload had items but none contained required fields")
    return records
