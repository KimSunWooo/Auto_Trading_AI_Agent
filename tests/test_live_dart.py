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
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    payload = {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "corp_name": "삼성전자",
                "corp_code": "00126380",
                "stock_code": "005930",
                "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
                "rcept_no": "20260921000001",
                "rcept_dt": "20260921",
            }
        ],
    }
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.OK
    assert result.items[0].kind is IntelligenceKind.CORPORATE_DISCLOSURE
    assert result.items[0].source == "opendart"
    assert result.items[0].headline.startswith("연결재무제표")


def test_dart_status_013_is_no_event(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    payload = {"status": "013", "message": "조회된 데이타가 없습니다.", "list": []}
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.NO_EVENT


def test_dart_unavailable_is_not_no_event(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    transport = FakeTransport(
        [
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
        ]
    )
    collector = LiveDisclosureCollector(
        client=_client(transport),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT
    assert collector.last_diagnostics is not None
    assert collector.last_diagnostics.status is CollectionStatus.DATA_UNAVAILABLE


def test_dart_auth_error_no_infinite_retry(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "bad-key-xxxxxxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    transport = FakeTransport([(401, b'{"status":"010"}')])
    client = _client(transport)
    collector = LiveDisclosureCollector(client=client, received_at_fn=lambda: AS_OF)
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert client.last_attempt_count == 1


def test_dart_missing_corp_mapping_is_refused(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.delenv("DART_CORP_CODE", raising=False)
    monkeypatch.delenv("DART_CORP_CODE_005930", raising=False)
    transport = FakeTransport([(200, b'{"status":"000","list":[]}')])
    collector = LiveDisclosureCollector(client=_client(transport), received_at_fn=lambda: AS_OF)
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert "MISSING_CORP_CODE" in (result.error or "")
    assert transport.responses  # HTTP was never consumed


def test_dart_mixed_companies_are_not_reattributed(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    payload = {
        "status": "000",
        "list": [
            {
                "corp_name": "다른회사",
                "corp_code": "00123456",
                "stock_code": "000660",
                "report_nm": "타사공시",
                "rcept_no": "20260921000002",
                "rcept_dt": "20260920",
            },
            {
                "corp_name": "삼성전자",
                "corp_code": "00126380",
                "stock_code": "005930",
                "report_nm": "자사공시",
                "rcept_no": "20260921000003",
                "rcept_dt": "20260920",
            },
        ],
    }
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.OK
    assert [item.ticker for item in result.items] == ["005930"]
    assert result.items[0].headline == "자사공시"


def test_dart_company_mismatch_all_rows(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    payload = {
        "status": "000",
        "list": [
            {
                "corp_name": "다른회사",
                "corp_code": "00999999",
                "stock_code": "000660",
                "report_nm": "타사",
                "rcept_no": "20260921000009",
                "rcept_dt": "20260920",
            }
        ],
    }
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert "COMPANY_MISMATCH" in (result.error or "")


def test_dart_pagination_and_mid_page_failure(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    page1 = {
        "status": "000",
        "total_page": 2,
        "list": [
            {
                "corp_name": "삼성전자",
                "corp_code": "00126380",
                "stock_code": "005930",
                "report_nm": "1페이지",
                "rcept_no": "20260921000011",
                "rcept_dt": "20260920",
            }
        ],
    }
    transport = FakeTransport(
        [
            (200, json.dumps(page1).encode()),
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
            ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True),
        ]
    )
    collector = LiveDisclosureCollector(
        client=_client(transport),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DEGRADED
    assert result.status is not CollectionStatus.NO_EVENT
    assert result.items
    assert collector.last_diagnostics is not None
    assert collector.last_diagnostics.error_code == "PAGINATION_INCOMPLETE"


def test_dart_full_page_without_total_page_is_degraded(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    rows = [
        {
            "corp_name": "삼성전자",
            "corp_code": "00126380",
            "stock_code": "005930",
            "report_nm": f"row{i}",
            "rcept_no": f"20260921000{i:03d}",
            "rcept_dt": "20260920",
        }
        for i in range(100)
    ]
    payload = {"status": "000", "list": rows}
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DEGRADED
    assert "PAGINATION_INCOMPLETE" in (result.error or "")


def test_dart_same_day_filing_not_visible_before_observed(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-dart-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    morning = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
    afternoon = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
    payload = {
        "status": "000",
        "list": [
            {
                "corp_name": "삼성전자",
                "corp_code": "00126380",
                "stock_code": "005930",
                "report_nm": "당일 오후 관측",
                "rcept_no": "20260921007777",
                "rcept_dt": "20260921",
            }
        ],
    }
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: afternoon,
    )
    morning_result = collector.collect("005930", morning)
    assert morning_result.status is CollectionStatus.NO_EVENT
    collector = LiveDisclosureCollector(
        client=_client(FakeTransport([(200, json.dumps(payload).encode())])),
        received_at_fn=lambda: afternoon,
    )
    afternoon_result = collector.collect("005930", afternoon)
    assert afternoon_result.status is CollectionStatus.OK
    item = afternoon_result.items[0]
    assert item.timestamps.source_received_at == afternoon
    assert item.timestamps.tradable_at == afternoon
    assert item.timestamps.published_at == datetime(2026, 9, 21, tzinfo=timezone.utc)
