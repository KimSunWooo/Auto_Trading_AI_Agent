"""Map OpenDART list responses into IntelligenceRecord values.

Titles are never turned into BUY/SELL directions here — Event Intelligence
owns classification. Official source ≠ positive investment signal.

rcept_dt is a date, not a timestamp. This parser keeps date precision
(midnight UTC of that date) and never invents an intra-day publish time.
sourceReceivedAt is the actual observation clock. tradableAt is not
backdated before that observation unless a stored snapshot already
recorded a better availability time.
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


def _normalize_corp(value: object | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.zfill(8) if text.isdigit() else text


def _normalize_stock(value: object | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.zfill(6) if text.isdigit() else text


def parse_rcept_dt(raw: str | None) -> datetime | None:
    """OpenDART rcept_dt is YYYYMMDD (date only). Midnight UTC marks the date."""
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


def dart_row_matches(
    row: dict[str, Any],
    *,
    ticker: str,
    corp_code: str,
) -> bool:
    row_corp = _normalize_corp(row.get("corp_code"))
    row_stock = _normalize_stock(row.get("stock_code"))
    expected_stock = _normalize_stock(ticker)
    expected_corp = _normalize_corp(corp_code)
    if not row_corp and not row_stock:
        return False
    if row_stock and row_stock != expected_stock:
        return False
    if row_corp and expected_corp and row_corp != expected_corp:
        return False
    return True


def dart_list_to_records(
    payload: dict[str, Any],
    *,
    ticker: str,
    collected_at: datetime,
    corp_code: str,
    received_at: datetime | None = None,
) -> tuple[list[IntelligenceRecord], int]:
    collected = _aware(collected_at)
    observed = _aware(received_at or collected_at)
    status = str(payload.get("status") or "")
    if status and status not in {"000", "013"}:
        raise ValueError(f"opendart status {status}: {payload.get('message')}")

    rows = payload.get("list") or []
    if not isinstance(rows, list):
        raise TypeError("opendart list must be an array")

    records: list[IntelligenceRecord] = []
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not dart_row_matches(row, ticker=ticker, corp_code=corp_code):
            rejected += 1
            continue
        title = str(row.get("report_nm") or row.get("title") or "").strip()
        if not title:
            continue
        rcept_no = str(row.get("rcept_no") or row.get("source_id") or "").strip()
        if not rcept_no:
            continue
        published = parse_rcept_dt(row.get("rcept_dt"))
        received = observed
        if published is not None and received < published:
            received = published
        tradable = received
        collected_ts = collected if collected >= received else received
        ts = CollectionTimestamps(
            event_occurred_at=published,
            published_at=published,
            source_received_at=received,
            collected_at=collected_ts,
            normalized_at=collected_ts,
            tradable_at=tradable,
        )
        body_parts = [
            f"corp_name={row.get('corp_name')}" if row.get("corp_name") else None,
            f"corp_cls={row.get('corp_cls')}" if row.get("corp_cls") else None,
            f"flr_nm={row.get('flr_nm')}" if row.get("flr_nm") else None,
            f"rm={row.get('rm')}" if row.get("rm") else None,
            "rcept_dt_precision=date",
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
    return records, rejected
