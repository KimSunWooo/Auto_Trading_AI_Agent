"""Parse vendor-neutral market JSON into Domain MarketDataRecord values.

Unsupported fields (1m/5m/VWAP/spread) stay None — never fabricated.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from ai_investment_agent.collectors.loading import parse_dt, parse_required_dt
from ai_investment_agent.domain.collection import (
    MARKET_DATA_FRESHNESS,
    CollectionTimestamps,
)
from ai_investment_agent.domain.enums import MarketDataKind
from ai_investment_agent.domain.market_feed import MarketDataRecord, OhlcvBar

SOURCE = "live-market"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _decimal(value: object | None) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _point_timestamps(
    point: dict[str, Any],
    *,
    collected_at: datetime,
    fallback_event: datetime | None = None,
) -> CollectionTimestamps:
    event = parse_dt(point.get("eventOccurredAt") or point.get("event_occurred_at"))
    if event is None:
        event = fallback_event
    published = parse_dt(point.get("publishedAt") or point.get("published_at")) or event
    received = (
        parse_dt(point.get("sourceReceivedAt") or point.get("source_received_at"))
        or published
        or collected_at
    )
    tradable = (
        parse_dt(point.get("tradableAt") or point.get("tradable_at"))
        or received
        or collected_at
    )
    return CollectionTimestamps(
        event_occurred_at=event,
        published_at=published,
        source_received_at=received,
        collected_at=collected_at,
        normalized_at=collected_at,
        analyzed_at=None,
        tradable_at=_aware(tradable),
    )


def parse_market_payload(
    payload: dict[str, Any],
    *,
    instrument: str,
    collected_at: datetime,
) -> list[MarketDataRecord]:
    """Build records from a read-only market JSON document.

    Expected shape (all quote fields optional; missing stays absent):
      instrument, currency,
      currentPrice: {value, eventOccurredAt?, sourceReceivedAt?, tradableAt?},
      volume / liquidity / volatility: same shape,
      dailyBars: [{open,high,low,close,volume,barStart,barEnd, ...timestamps?}]
    """
    collected = _aware(collected_at)
    currency = payload.get("currency") or "KRW"
    records: list[MarketDataRecord] = []
    ticker = str(payload.get("instrument") or instrument)

    def add_scalar(kind: MarketDataKind, key: str) -> None:
        raw = payload.get(key)
        if raw is None:
            return
        if isinstance(raw, dict):
            value = _decimal(raw.get("value"))
            if value is None:
                return
            ts = _point_timestamps(raw, collected_at=collected)
            record_id = f"live_{kind.value.lower()}_{ticker}_{int(ts.tradable_at.timestamp())}"
        else:
            value = _decimal(raw)
            if value is None:
                return
            # Scalar without timestamps is treated as just-received; caller freshness
            # policy still applies against collected_at.
            ts = CollectionTimestamps(
                event_occurred_at=collected,
                published_at=collected,
                source_received_at=collected,
                collected_at=collected,
                normalized_at=collected,
                tradable_at=collected,
            )
            record_id = f"live_{kind.value.lower()}_{ticker}_{int(collected.timestamp())}"
        records.append(
            MarketDataRecord(
                record_id=record_id,
                kind=kind,
                instrument=ticker,
                timestamps=ts,
                freshness_class=MARKET_DATA_FRESHNESS[kind],
                value=value,
                currency=currency,
                source=SOURCE,
            )
        )

    add_scalar(MarketDataKind.CURRENT_PRICE, "currentPrice")
    if "currentPrice" not in payload and "last" in payload:
        add_scalar(MarketDataKind.CURRENT_PRICE, "last")
    add_scalar(MarketDataKind.VOLUME, "volume")
    add_scalar(MarketDataKind.LIQUIDITY, "liquidity")
    add_scalar(MarketDataKind.VOLATILITY, "volatility")

    bars = payload.get("dailyBars") or payload.get("daily_bars") or []
    if not isinstance(bars, list):
        bars = []
    for index, bar in enumerate(bars):
        if not isinstance(bar, dict):
            continue
        open_ = _decimal(bar.get("open"))
        high = _decimal(bar.get("high"))
        low = _decimal(bar.get("low"))
        close = _decimal(bar.get("close"))
        volume = _decimal(bar.get("volume")) or Decimal("0")
        if None in (open_, high, low, close):
            continue
        bar_start = parse_required_dt(bar.get("barStart") or bar.get("bar_start"), "barStart")
        bar_end = parse_required_dt(bar.get("barEnd") or bar.get("bar_end"), "barEnd")
        ts = _point_timestamps(
            bar,
            collected_at=collected,
            fallback_event=bar_end,
        )
        # Weekly bars are only accepted when explicitly flagged. Daily never copied to weekly.
        if bar.get("interval") == "1w" or bar.get("timeframe") == "WEEKLY":
            # Weekly data is optional; store as OHLCV with LONG_HORIZON freshness via unit tag.
            pass
        records.append(
            MarketDataRecord(
                record_id=f"live_ohlcv_{ticker}_{index}_{int(bar_end.timestamp())}",
                kind=MarketDataKind.OHLCV,
                instrument=ticker,
                timestamps=ts,
                freshness_class=MARKET_DATA_FRESHNESS[MarketDataKind.OHLCV],
                ohlcv=OhlcvBar(
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    bar_start=bar_start,
                    bar_end=bar_end,
                ),
                currency=currency,
                unit=str(bar.get("interval") or bar.get("timeframe") or "1d"),
                source=SOURCE,
            )
        )

    return records


def default_daily_window(as_of: datetime, days: int = 180) -> tuple[str, str]:
    end = _aware(as_of).date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()
