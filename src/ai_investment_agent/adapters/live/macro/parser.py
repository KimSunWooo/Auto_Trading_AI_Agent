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
    items = payload.get("items") or payload.get("observations") or payload.get("list") or []
    if isinstance(payload.get("headline"), str) and not items:
        items = [payload]
    if not isinstance(items, list):
        raise TypeError("macro items must be a list")

    records: list[IntelligenceRecord] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        headline = str(item.get("headline") or item.get("title") or item.get("series_id") or "").strip()
        if not headline:
            continue
        kind_raw = str(item.get("kind") or item.get("category") or "ECONOMIC_INDICATOR").upper()
        kind = KIND_MAP.get(kind_raw, IntelligenceKind.ECONOMIC_INDICATOR)
        published = (
            parse_dt(item.get("publishedAt") or item.get("published_at") or item.get("date"))
            or collected
        )
        received = parse_dt(item.get("sourceReceivedAt") or item.get("source_received_at"))
        if received is None:
            received = published
        if received < published:
            received = published
        collected_ts = collected if collected >= received else received
        ts = CollectionTimestamps(
            event_occurred_at=parse_dt(item.get("eventOccurredAt") or item.get("event_occurred_at"))
            or published,
            published_at=published,
            source_received_at=received,
            collected_at=collected_ts,
            normalized_at=collected_ts,
            tradable_at=received,
        )
        # Store actual/consensus/previous as structured body for Macro Feature Engine.
        # Never invent consensus.
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
    return records
