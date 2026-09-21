from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from ai_investment_agent.domain.enums import EventSeverity, MarketRegimeType
from ai_investment_agent.domain.ids import new_event_id
from ai_investment_agent.domain.market import MarketEvent, MarketSnapshot

DATA_DIR = Path(__file__).resolve().parent / "data"


def _dt(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def load_json(name: str) -> dict:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def snapshot_from_dict(raw: dict) -> MarketSnapshot:
    hint = raw.get("regimeHint") or raw.get("regime_hint")
    return MarketSnapshot(
        ticker=raw["ticker"],
        as_of=_dt(raw.get("asOf") or raw.get("as_of")),
        last_price=_decimal(raw.get("lastPrice", raw.get("last_price"))),
        currency=raw.get("currency", "KRW"),
        open_price=_decimal(raw.get("openPrice", raw.get("open_price"))),
        high_price=_decimal(raw.get("highPrice", raw.get("high_price"))),
        low_price=_decimal(raw.get("lowPrice", raw.get("low_price"))),
        volume=_decimal(raw.get("volume")),
        volatility=_decimal(raw.get("volatility")),
        liquidity_score=_decimal(raw.get("liquidityScore", raw.get("liquidity_score"))),
        data_completeness=Decimal(str(raw.get("dataCompleteness", raw.get("data_completeness", "1")))),
        regime_hint=MarketRegimeType(hint) if hint else None,
        source=raw.get("source", "fixture"),
    )


def event_from_dict(raw: dict) -> MarketEvent:
    return MarketEvent(
        event_id=raw.get("eventId") or raw.get("event_id") or new_event_id(),
        ticker=raw.get("ticker"),
        event_type=raw.get("eventType") or raw.get("event_type") or "OTHER",
        title=raw["title"],
        occurred_at=_dt(raw.get("occurredAt") or raw.get("occurred_at")),
        severity=EventSeverity(raw.get("severity", "INFO")),
        source=raw.get("source", "fixture"),
        payload=raw.get("payload") or {},
    )


class FixtureMarketDataProvider:
    def __init__(self, snapshots: dict[str, MarketSnapshot] | None = None) -> None:
        self._snapshots = snapshots or {}

    @classmethod
    def from_files(cls, *names: str) -> FixtureMarketDataProvider:
        provider = cls()
        for name in names:
            provider.add(snapshot_from_dict(load_json(name)))
        return provider

    def add(self, snapshot: MarketSnapshot) -> None:
        self._snapshots[snapshot.ticker] = snapshot

    def get_snapshot(self, ticker: str) -> MarketSnapshot:
        if ticker not in self._snapshots:
            raise KeyError(f"No fixture snapshot for ticker {ticker}")
        return self._snapshots[ticker]


class FixtureEventProvider:
    def __init__(self, events: dict[str, list[MarketEvent]] | None = None) -> None:
        self._events = events or {}

    @classmethod
    def from_file(cls, name: str) -> FixtureEventProvider:
        raw = load_json(name)
        grouped: dict[str, list[MarketEvent]] = {}
        for item in raw.get("events", []):
            event = event_from_dict(item)
            key = event.ticker or "*"
            grouped.setdefault(key, []).append(event)
        return cls(grouped)

    def get_events(self, ticker: str) -> list[MarketEvent]:
        return list(self._events.get(ticker, [])) + list(self._events.get("*", []))
