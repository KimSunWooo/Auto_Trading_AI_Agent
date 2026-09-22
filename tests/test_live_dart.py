"""10.5.3 OpenDART disclosure adapter tests (mocked; no network)."""

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
from ai_investment_agent.adapters.live.dart import LiveDisclosureCollector
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
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
        name="dart",
        base_url="https://example.test/api",
        api_key_env="DART_API_KEY",
        timeout=HttpTimeoutConfig(total_seconds=5.0),
        retry=RetryConfig(max_attempts=2, base_backoff_seconds=0.0),
        rate_limit=RateLimitConfig(max_requests_per_second=100.0),
        circuit=CircuitBreakerConfig(failure_threshold=5, cooldown_seconds=30.0),
    )
    client = ProviderHttpClient(config=cfg, transport=transport)
    client.sleep_fn = lambda _s: None
    return client


AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def test_dart_ok_disclosures(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    payload = {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "corp_name": "삼성전자",
                "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
                "rcept_no": "20260921000001",
                "rcept_dt": "20260921",
            }
        ],
    }
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())]))
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.OK
    assert result.items[0].kind is IntelligenceKind.CORPORATE_DISCLOSURE
    assert result.items[0].source == "opendart"
    assert result.items[0].headline.startswith("연결재무제표")


def test_dart_status_013_is_no_event(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    payload = {"status": "013", "message": "조회된 데이타가 없습니다.", "list": []}
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())]))
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.NO_EVENT


def test_dart_unavailable_is_not_no_event(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    transport = FakeTransport(
        [
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
        ]
    )
    collector = LiveDisclosureCollector(client=_client(transport))
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT
    assert collector.last_diagnostics is not None
    assert collector.last_diagnostics.status is CollectionStatus.DATA_UNAVAILABLE


def test_dart_auth_error_no_infinite_retry(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "bad-key-xxxxxxxxxxxx")
    transport = FakeTransport([(401, b'{"status":"010"}')])
    client = _client(transport)
    collector = LiveDisclosureCollector(client=client)
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert client.last_attempt_count == 1
