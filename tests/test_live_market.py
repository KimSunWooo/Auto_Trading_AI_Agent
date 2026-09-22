"""10.5.2 Live Market Data adapter tests (mocked HTTP; no network)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Mapping

import pytest

from ai_investment_agent.adapters.live.config import (
    CircuitBreakerConfig,
    HttpTimeoutConfig,
    ProviderHttpConfig,
    RateLimitConfig,
    RetryConfig,
)
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
from ai_investment_agent.adapters.live.market import (
    FORBIDDEN_MARKET_METHODS,
    LiveMarketDataCollector,
)
from ai_investment_agent.domain.enums import CollectionStatus, MarketDataKind


class FakeTransport:
    def __init__(self, responses: list[tuple[int, bytes] | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        connect_timeout: float,
        read_timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(transport: FakeTransport) -> ProviderHttpClient:
    cfg = ProviderHttpConfig(
        name="market",
        base_url="https://md.example",
        api_key_env=None,
        timeout=HttpTimeoutConfig(total_seconds=5.0),
        retry=RetryConfig(max_attempts=2, base_backoff_seconds=0.0),
        rate_limit=RateLimitConfig(max_requests_per_second=100.0),
        circuit=CircuitBreakerConfig(failure_threshold=5, cooldown_seconds=30.0),
    )
    client = ProviderHttpClient(config=cfg, transport=transport)
    client.sleep_fn = lambda _s: None
    return client


AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def _fresh_payload() -> dict:
    ts = "2026-09-21T08:59:30+00:00"
    return {
        "instrument": "005930",
        "currency": "KRW",
        "currentPrice": {
            "value": "71000",
            "eventOccurredAt": ts,
            "sourceReceivedAt": "2026-09-21T08:59:31+00:00",
            "tradableAt": "2026-09-21T08:59:31+00:00",
        },
        "volume": {
            "value": "12000000",
            "eventOccurredAt": ts,
            "sourceReceivedAt": "2026-09-21T08:59:31+00:00",
            "tradableAt": "2026-09-21T08:59:31+00:00",
        },
        "liquidity": {
            "value": "0.85",
            "eventOccurredAt": ts,
            "sourceReceivedAt": "2026-09-21T08:59:31+00:00",
            "tradableAt": "2026-09-21T08:59:31+00:00",
        },
        "dailyBars": [
            {
                "open": "70000",
                "high": "71500",
                "low": "69500",
                "close": "71000",
                "volume": "10000000",
                "barStart": "2026-09-20T00:00:00+00:00",
                "barEnd": "2026-09-20T06:00:00+00:00",
                "eventOccurredAt": "2026-09-20T06:00:00+00:00",
                "sourceReceivedAt": "2026-09-20T06:00:05+00:00",
                "tradableAt": "2026-09-20T06:00:05+00:00",
                "interval": "1d",
            }
        ],
    }


def test_live_market_ok():
    body = json.dumps(_fresh_payload()).encode()
    transport = FakeTransport([(200, body)])
    collector = LiveMarketDataCollector(client=_client(transport))
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.OK
    assert any(item.kind is MarketDataKind.CURRENT_PRICE for item in result.items)
    assert any(item.kind is MarketDataKind.OHLCV for item in result.items)
    assert collector.last_diagnostics is not None
    assert collector.last_diagnostics.status is CollectionStatus.OK
    assert all(item.source == "live-market" for item in result.items)
    assert "order" not in transport.calls[0]


def test_live_market_timeout_is_data_unavailable():
    transport = FakeTransport(
        [
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
        ]
    )
    collector = LiveMarketDataCollector(client=_client(transport))
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT
    assert collector.last_diagnostics is not None
    assert collector.last_diagnostics.error_code == "TIMEOUT"


def test_live_market_stale_blocks_freshness():
    stale_ts = (AS_OF - timedelta(hours=2)).isoformat()
    payload = _fresh_payload()
    payload["currentPrice"] = {
        "value": "71000",
        "eventOccurredAt": stale_ts,
        "sourceReceivedAt": stale_ts,
        "tradableAt": stale_ts,
    }
    payload.pop("volume")
    payload.pop("liquidity")
    payload["dailyBars"] = []
    transport = FakeTransport([(200, json.dumps(payload).encode())])
    collector = LiveMarketDataCollector(client=_client(transport))
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.STALE


def test_no_fabricated_intraday_fields():
    payload = _fresh_payload()
    transport = FakeTransport([(200, json.dumps(payload).encode())])
    collector = LiveMarketDataCollector(client=_client(transport))
    result = collector.collect("005930", AS_OF)
    for item in result.items:
        assert item.ohlcv is None or item.unit in {None, "1d", "1w", "WEEKLY"}


def test_forbidden_order_methods_not_on_collector():
    names = set(dir(LiveMarketDataCollector))
    assert names.isdisjoint(FORBIDDEN_MARKET_METHODS)
    assert not hasattr(LiveMarketDataCollector, "place_order")
    assert not hasattr(LiveMarketDataCollector, "submit_order")
