"""Map OpenDART list responses into IntelligenceRecord values.

Titles are never turned into BUY/SELL directions here — Event Intelligence
owns classification. Official source ≠ positive investment signal.
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

SOURCE = "opendart"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_rcept_dt(raw: str | None) -> datetime | None:
    """OpenDART rcept_dt is YYYYMMDD. Time-of-day is not provided → midnight UTC."""
    if not raw:
        return None
    text = str(raw).strip()
    if len(text) == 8 and text.isdigit():
        return datetime(
            int(text[0:4]),
            int(text[4:6]),
            int(text[6:8]),
            tzinfo=timezone.utc,
        )
    return parse_dt(text)


def dart_list_to_records(
    payload: dict[str, Any],
    *,
    ticker: str,
    collected_at: datetime,
) -> list[IntelligenceRecord]:
    collected = _aware(collected_at)
    status = str(payload.get("status") or "")
    if status and status not in {"000", "013"}:
        # Non-success OpenDART status codes are handled by the collector as unavailable.
        raise ValueError(f"opendart status {status}: {payload.get('message')}")

    rows = payload.get("list") or []
    if not isinstance(rows, list):
        raise TypeError("opendart list must be an array")

    records: list[IntelligenceRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("report_nm") or row.get("title") or "").strip()
        if not title:
            continue
        rcept_no = str(row.get("rcept_no") or row.get("source_id") or "").strip()
        if not rcept_no:
            continue
        # Official DART availability follows rcept_dt, not wall-clock fetch time.
        # Using fetch-time as sourceReceivedAt would look-ahead-block historical as_of.
        published = parse_rcept_dt(row.get("rcept_dt")) or collected
        received = published
        collected_ts = collected if collected >= received else received
        ts = CollectionTimestamps(
            event_occurred_at=published,
            published_at=published,
            source_received_at=received,
            collected_at=collected_ts,
            normalized_at=collected_ts,
            tradable_at=received,
        )
        body_parts = [
            f"corp_name={row.get('corp_name')}" if row.get("corp_name") else None,
            f"corp_cls={row.get('corp_cls')}" if row.get("corp_cls") else None,
            f"flr_nm={row.get('flr_nm')}" if row.get("flr_nm") else None,
            f"rm={row.get('rm')}" if row.get("rm") else None,
        ]
        body = "; ".join(part for part in body_parts if part)
        records.append(
            IntelligenceRecord(
                record_id=f"dart_{rcept_no}",
                kind=IntelligenceKind.CORPORATE_DISCLOSURE,
                headline=title,
                timestamps=ts,
                freshness_class=INTELLIGENCE_FRESHNESS[IntelligenceKind.CORPORATE_DISCLOSURE],
                ticker=ticker,
                body=body or None,
                source=SOURCE,
                language="ko",
                country="KR",
                raw_ref=rcept_no,
            )
        )
    return records
