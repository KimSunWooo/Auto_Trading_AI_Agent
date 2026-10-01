"""10.5.4 Macro adapter tests (mocked; no network)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping

from ai_investment_agent.adapters.live.config import (
    CircuitBreakerConfig,
    HttpTimeoutConfig,
    ProviderHttpConfig,
    RateLimitConfig,
    RetryConfig,
)
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
from ai_investment_agent.adapters.live.macro import LiveMacroCollector
from ai_investment_agent.domain.enums import CollectionStatus, IntelligenceKind


class FakeTransport:
    def __init__(self, responses: list[tuple[int, bytes] | Exception]) -> None:
        self.responses = list(responses)

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
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(transport: FakeTransport) -> ProviderHttpClient:
    cfg = ProviderHttpConfig(
        name="macro",
        base_url="https://macro.example",
        api_key_env="MACRO_API_KEY",
        timeout=HttpTimeoutConfig(total_seconds=5.0),
        retry=RetryConfig(max_attempts=2, base_backoff_seconds=0.0),
        rate_limit=RateLimitConfig(max_requests_per_second=100.0),
        circuit=CircuitBreakerConfig(failure_threshold=5, cooldown_seconds=30.0),
    )
    client = ProviderHttpClient(config=cfg, transport=transport)
    client.sleep_fn = lambda _s: None
    return client


AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def test_macro_ok_preserves_consensus_none():
    payload = {
        "items": [
            {
                "id": "bok_rate_2026",
                "kind": "CENTRAL_BANK",
                "headline": "한국은행 기준금리 결정",
                "publishedAt": "2026-09-20T06:00:00+00:00",
                "actual": "2.50",
                "previous": "2.50",
                "source": "bok",
                "country": "KR",
            }
        ]
    }
    collector = LiveMacroCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect(AS_OF)
    assert result.status is CollectionStatus.OK
    assert result.items[0].kind is IntelligenceKind.CENTRAL_BANK
    assert "consensus=None" in (result.items[0].body or "")
    assert "actual=2.50" in (result.items[0].body or "")


def test_macro_no_event_status():
    payload = {"status": "NO_EVENT", "items": []}
    collector = LiveMacroCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect(AS_OF)
    assert result.status is CollectionStatus.NO_EVENT


def test_macro_timeout_not_no_event():
    transport = FakeTransport(
        [
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
        ]
    )
    collector = LiveMacroCollector(client=_client(transport), received_at_fn=lambda: AS_OF)
    result = collector.collect(AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT
