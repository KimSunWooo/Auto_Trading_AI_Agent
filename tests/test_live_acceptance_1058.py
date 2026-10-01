"""10.5.8 acceptance: reproduce remaining defects with advancing clocks.

These tests use existing public APIs. A new-import failure is not treated
as proof of the original bug.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import pytest

from ai_investment_agent.adapters.live.config import (
    CircuitBreakerConfig,
    HttpTimeoutConfig,
    ProviderHttpConfig,
    RateLimitConfig,
    RetryConfig,
)
from ai_investment_agent.adapters.live.dart import LiveDisclosureCollector
from ai_investment_agent.adapters.live.factory import build_live_observation_service
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
from ai_investment_agent.adapters.live.llm import LiveLlmProvider
from ai_investment_agent.adapters.live.macro import LiveMacroCollector
from ai_investment_agent.adapters.live.market import LiveMarketDataCollector
from ai_investment_agent.adapters.live.news import LiveNewsCollector
from ai_investment_agent.adapters.live.news.parser import parse_news_payload
from ai_investment_agent.analysis.service import merge_external_status
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import (
    Action,
    CollectionStatus,
    KillSwitchLevel,
    PolicyState,
)
from ai_investment_agent.ports.llm import LlmResponse
from tests.horizon_support import bullish_long, good_entry, judge, weak_short
from tests.test_live_observation import FakeTransport, _client, _llm_payload, _market_payload
from tests.test_provider_framework import FakeTransport as SeqTransport
from tests.test_provider_framework import _config


T0 = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def _dart_row(rcept_no: str = "20260921000001", **extra: object) -> dict:
    row = {
        "corp_name": "삼성전자",
        "corp_code": "00126380",
        "stock_code": "005930",
        "report_nm": "연결실적",
        "rcept_no": rcept_no,
        "rcept_dt": "20260921",
    }
    row.update(extra)
    return row


def test_live_current_observation_keeps_data_received_after_request_start(monkeypatch):
    """as_of omitted: receive at t0+lag must still be usable. Do not pin receive==as_of."""
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-xxxxxxxxxxxx")
    clock = {"now": T0}

    def now() -> datetime:
        return clock["now"]

    def dart_received() -> datetime:
        clock["now"] = T0 + timedelta(seconds=45)
        return clock["now"]

    dart_t = FakeTransport(
        {"/list.json": (200, json.dumps({"status": "000", "list": [_dart_row()]}).encode())}
    )
    market_t = FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())})
    macro_t = FakeTransport({"/macro": (200, json.dumps({"status": "NO_EVENT", "items": []}).encode())})
    news_t = FakeTransport({"/news": (200, json.dumps({"status": "NO_EVENT", "articles": []}).encode())})
    llm_t = FakeTransport({"/chat/completions": (200, _llm_payload())})
    service = build_live_observation_service(
        now_fn=now,
        market=LiveMarketDataCollector(client=_client("market", "https://md.example", market_t)),
        disclosure=LiveDisclosureCollector(
            client=_client("dart", "https://example.test/api", dart_t, "DART_API_KEY"),
            received_at_fn=dart_received,
        ),
        macro=LiveMacroCollector(
            client=_client("macro", "https://macro.example", macro_t),
            received_at_fn=lambda: T0 + timedelta(seconds=20),
        ),
        news=LiveNewsCollector(
            client=_client("news", "https://news.example", news_t),
            received_at_fn=lambda: T0 + timedelta(seconds=10),
        ),
    )
    service.llm = LiveLlmProvider(client=_client("llm", "https://llm.example/v1", llm_t, "LLM_API_KEY"))
    result = service.evaluate("005930")
    disclosure = next(item for item in result.provider_health if item.name == "disclosure")
    assert disclosure.status is CollectionStatus.OK
    assert service.disclosure.last_diagnostics is not None
    items = service.last_external.items if service.last_external else []
    dart_items = [item for item in items if item.source == "opendart"]
    assert dart_items, "live current observation dropped data received after t0"
    assert dart_items[0].timestamps.source_received_at > T0
    assert dart_items[0].timestamps.source_received_at <= result.snapshot.analysis_as_of
    assert result.snapshot.created_at >= dart_items[0].timestamps.source_received_at


def test_explicit_past_as_of_does_not_backdate_later_receive(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    past = T0
    receive = T0 + timedelta(hours=6)
    collector = LiveDisclosureCollector(
        client=_client(
            "dart",
            "https://example.test/api",
            FakeTransport(
                {"/list.json": (200, json.dumps({"status": "000", "list": [_dart_row()]}).encode())}
            ),
            "DART_API_KEY",
        ),
        received_at_fn=lambda: receive,
    )
    result = collector.collect("005930", past)
    assert result.items == []
    assert result.status is CollectionStatus.NO_EVENT


def test_dart_degraded_is_not_merged_to_overall_ok():
    as_of = T0
    disclosure = CollectionResult.degraded(
        [],
        error="PAGINATION_INCOMPLETE: page 2 failed",
        as_of=as_of,
    )
    quiet = CollectionResult.no_event(as_of=as_of)
    status, error = merge_external_status(
        {
            "news": quiet,
            "disclosure": disclosure,
            "macro": quiet,
            "scheduledEvent": CollectionResult.unavailable(
                error="scheduledEvent NOT_CONFIGURED: live calendar provider is not configured",
                as_of=as_of,
            ),
        }
    )
    assert status is CollectionStatus.DEGRADED
    assert status is not CollectionStatus.OK
    assert error is not None
    assert "disclosure" in error or "PAGINATION" in error


def test_deadline_elapsed_response_is_not_success():
    clock = [0.0]

    class LateTransport:
        def request(self, method, url, *, headers, body, connect_timeout, read_timeout):
            clock[0] += 5.0
            return 200, b'{"ok":true}'

    cfg = _config(
        timeout=HttpTimeoutConfig(total_seconds=1.0, connect_seconds=5.0, read_seconds=5.0),
        retry=RetryConfig(max_attempts=1),
        rate_limit=RateLimitConfig(max_requests_per_second=0),
    )
    client = ProviderHttpClient(
        config=cfg,
        transport=LateTransport(),
        monotonic_fn=lambda: clock[0],
        sleep_fn=lambda _s: None,
    )
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/late")
    assert exc.value.error_code == "TIMEOUT"
    assert client.circuit.failures >= 1
    assert not client.circuit.allow(clock[0]) or client.circuit.failures >= 1


def test_news_ids_include_source_and_avoid_index_only_identity():
    collected = T0
    reuters = parse_news_payload(
        {
            "articles": [
                {
                    "id": "same-id",
                    "title": "One",
                    "publishedAt": "2026-09-21T07:00:00+00:00",
                    "source": "reuters",
                    "kind": "FOREIGN_NEWS",
                    "ticker": "005930",
                }
            ]
        },
        ticker="005930",
        collected_at=collected,
    )
    bloomberg = parse_news_payload(
        {
            "articles": [
                {
                    "id": "same-id",
                    "title": "One",
                    "publishedAt": "2026-09-21T07:00:00+00:00",
                    "source": "bloomberg",
                    "kind": "FOREIGN_NEWS",
                    "ticker": "005930",
                }
            ]
        },
        ticker="005930",
        collected_at=collected,
    )
    assert reuters[0].record_id != bloomberg[0].record_id

    first = parse_news_payload(
        {
            "articles": [
                {
                    "title": "No id headline",
                    "publishedAt": "2026-09-21T07:00:00+00:00",
                    "source": "wire-a",
                    "kind": "DOMESTIC_NEWS",
                    "ticker": "005930",
                }
            ]
        },
        ticker="005930",
        collected_at=collected,
    )
    reordered = parse_news_payload(
        {
            "articles": [
                {
                    "title": "Other",
                    "publishedAt": "2026-09-21T06:00:00+00:00",
                    "source": "wire-a",
                    "kind": "DOMESTIC_NEWS",
                    "ticker": "005930",
                },
                {
                    "title": "No id headline",
                    "publishedAt": "2026-09-21T07:00:00+00:00",
                    "source": "wire-a",
                    "kind": "DOMESTIC_NEWS",
                    "ticker": "005930",
                },
            ]
        },
        ticker="005930",
        collected_at=collected,
    )
    matching = [item for item in reordered if item.headline == "No id headline"]
    assert matching
    assert matching[0].record_id == first[0].record_id
    assert "news_0:" not in first[0].record_id


def test_mixed_valid_and_corrupt_ohlcv_is_degraded_not_ok():
    payload = {
        "instrument": "005930",
        "currency": "KRW",
        "currentPrice": {
            "value": "71000",
            "eventOccurredAt": "2026-09-21T08:59:30+00:00",
            "sourceReceivedAt": "2026-09-21T08:59:31+00:00",
            "tradableAt": "2026-09-21T08:59:31+00:00",
        },
        "dailyBars": [
            {
                "open": "1",
                "high": "2",
                "low": "0.5",
                "close": "1.5",
                "volume": "10",
                "barStart": "2026-09-20T00:00:00+00:00",
                "barEnd": "2026-09-20T06:00:00+00:00",
                "eventOccurredAt": "2026-09-20T06:00:00+00:00",
                "sourceReceivedAt": "2026-09-20T06:00:05+00:00",
                "tradableAt": "2026-09-20T06:00:05+00:00",
            },
            {
                "open": "1",
                "high": "2",
                "low": "0.5",
                "close": "1.5",
                "barStart": "2026-09-19T00:00:00+00:00",
                "barEnd": "2026-09-19T06:00:00+00:00",
            },
        ],
    }
    collector = LiveMarketDataCollector(
        client=ProviderHttpClient(
            config=ProviderHttpConfig(
                name="market",
                base_url="https://md.example",
                api_key_env=None,
                timeout=HttpTimeoutConfig(total_seconds=5.0),
                retry=RetryConfig(max_attempts=1),
                rate_limit=RateLimitConfig(max_requests_per_second=100.0),
                circuit=CircuitBreakerConfig(failure_threshold=5, cooldown_seconds=30.0),
            ),
            transport=FakeTransport({"/market/": (200, json.dumps(payload).encode())}),
        )
    )
    result = collector.collect("005930", T0)
    assert result.status is CollectionStatus.DEGRADED
    assert result.items
    assert result.status is not CollectionStatus.OK


def test_llm_diagnostics_follow_the_latest_call_not_the_previous(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-xxxxxxxxxxxx")
    class FlipTransport:
        def __init__(self) -> None:
            self.calls = 0

        def request(self, method, url, *, headers, body, connect_timeout, read_timeout):
            self.calls += 1
            if self.calls == 1:
                return 200, _llm_payload()
            return 200, json.dumps(
                {"model": "gpt-test", "choices": [{"message": {"content": "not-json{{{"}}]}
            ).encode()

    market_t = FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())})
    dart_t = FakeTransport({"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())})
    macro_t = FakeTransport({"/macro": (200, json.dumps({"status": "NO_EVENT", "items": []}).encode())})
    news_t = FakeTransport({"/news": (200, json.dumps({"status": "NO_EVENT", "articles": []}).encode())})
    flip = FlipTransport()
    service = build_live_observation_service(
        now_fn=lambda: T0,
        market=LiveMarketDataCollector(client=_client("market", "https://md.example", market_t)),
        disclosure=LiveDisclosureCollector(
            client=_client("dart", "https://example.test/api", dart_t, "DART_API_KEY"),
            received_at_fn=lambda: T0,
        ),
        macro=LiveMacroCollector(
            client=_client("macro", "https://macro.example", macro_t),
            received_at_fn=lambda: T0,
        ),
        news=LiveNewsCollector(
            client=_client("news", "https://news.example", news_t),
            received_at_fn=lambda: T0,
        ),
    )
    service.llm = LiveLlmProvider(client=_client("llm", "https://llm.example/v1", flip, "LLM_API_KEY"))
    first = service.evaluate("005930", as_of=T0)
    assert service.provider_diagnostics["llm"].status is CollectionStatus.OK
    second = service.evaluate("005930", as_of=T0)
    assert second.action is Action.NO_TRADE
    assert service.provider_diagnostics["llm"].status is CollectionStatus.DATA_UNAVAILABLE
    assert service.provider_diagnostics["llm"].error_code == "LLM_INVALID_JSON"
    assert first.action is not None


def test_llm_buy_cannot_bypass_kill_switch():
    assist = LlmResponse(
        content={
            "desiredDecision": "LONG_TERM_BUY",
            "rawConfidence": 0.99,
            "suggestedCapitalPct": "40",
            "llmStatus": "OK",
            "promptVersion": "0.1.0-live",
            "thesis": {
                "headline": "Buy",
                "summary": "LLM buy",
                "bullCase": "x",
                "bearCase": "y",
                "timeHorizon": "LONG_TERM",
            },
        },
        model_name="gpt-test",
    )
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
        kill_switch_level=KillSwitchLevel.LEVEL_1_NO_NEW_BUY,
        policy_state=PolicyState.NORMAL,
        llm_assist=assist,
    )
    assert snapshot.proposal.action is not Action.BUY


def test_dart_duplicate_pages_do_not_duplicate_records(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    page = {
        "status": "000",
        "total_page": 2,
        "list": [_dart_row("20260921000001")],
    }
    transport = SeqTransport(
        [
            (200, json.dumps(page).encode()),
            (200, json.dumps(page).encode()),
        ]
    )
    collector = LiveDisclosureCollector(
        client=ProviderHttpClient(
            config=ProviderHttpConfig(
                name="dart",
                base_url="https://example.test/api",
                api_key_env="DART_API_KEY",
                timeout=HttpTimeoutConfig(total_seconds=5.0),
                retry=RetryConfig(max_attempts=1),
                rate_limit=RateLimitConfig(max_requests_per_second=100.0),
                circuit=CircuitBreakerConfig(failure_threshold=5, cooldown_seconds=30.0),
            ),
            transport=transport,
        ),
        received_at_fn=lambda: T0 + timedelta(seconds=12),
    )
    result = collector.collect("005930", T0 + timedelta(seconds=12))
    assert result.status is CollectionStatus.OK
    ids = [item.record_id for item in result.items]
    assert ids == list(dict.fromkeys(ids))


def test_replay_restores_snapshot_without_live_calls(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-xxxxxxxxxxxx")
    market_t = FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())})
    dart_t = FakeTransport({"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())})
    macro_t = FakeTransport({"/macro": (200, json.dumps({"status": "NO_EVENT", "items": []}).encode())})
    news_t = FakeTransport({"/news": (200, json.dumps({"status": "NO_EVENT", "articles": []}).encode())})
    llm_t = FakeTransport({"/chat/completions": (200, _llm_payload())})
    service = build_live_observation_service(
        now_fn=lambda: T0,
        market=LiveMarketDataCollector(client=_client("market", "https://md.example", market_t)),
        disclosure=LiveDisclosureCollector(
            client=_client("dart", "https://example.test/api", dart_t, "DART_API_KEY"),
            received_at_fn=lambda: T0,
        ),
        macro=LiveMacroCollector(
            client=_client("macro", "https://macro.example", macro_t),
            received_at_fn=lambda: T0,
        ),
        news=LiveNewsCollector(
            client=_client("news", "https://news.example", news_t),
            received_at_fn=lambda: T0,
        ),
    )
    service.llm = LiveLlmProvider(client=_client("llm", "https://llm.example/v1", llm_t, "LLM_API_KEY"))
    result = service.evaluate("005930", as_of=T0)
    calls_before = len(market_t.calls)
    bundle = service.replay_decision(result.decision_id)
    assert bundle.deterministic_rerun is False
    assert "not re-executed" in bundle.restore_note.lower() or "not re-executed" in bundle.restore_note
    assert len(market_t.calls) == calls_before
    assert bundle.proposal.action is result.action
    assert bundle.proposal.is_order is False if hasattr(bundle.proposal, "is_order") else True
