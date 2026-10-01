"""10.5.8 Live must not ingest fixture scheduled-event rows."""

from __future__ import annotations

import json

from ai_investment_agent.adapters.live.dart import LiveDisclosureCollector
from ai_investment_agent.adapters.live.factory import build_live_observation_service
from ai_investment_agent.adapters.live.llm import LiveLlmProvider
from ai_investment_agent.adapters.live.macro import LiveMacroCollector
from ai_investment_agent.adapters.live.market import LiveMarketDataCollector
from ai_investment_agent.adapters.live.news import LiveNewsCollector
from ai_investment_agent.adapters.live.scheduled import UnconfiguredScheduledEventCollector
from ai_investment_agent.collectors.intelligence import FixtureScheduledEventCollector
from ai_investment_agent.domain.enums import CollectionStatus, DataMode
from tests.test_live_observation import (
    AS_OF,
    FakeTransport,
    _client,
    _llm_payload,
    _market_payload,
)


def _live_service(monkeypatch, scheduled_env: str | None):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-xxxxxxxxxxxx")
    if scheduled_env is None:
        monkeypatch.delenv("SCHEDULED_USE_FIXTURE", raising=False)
    else:
        monkeypatch.setenv("SCHEDULED_USE_FIXTURE", scheduled_env)
    market_t = FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())})
    dart_t = FakeTransport({"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())})
    macro_t = FakeTransport({"/macro": (200, json.dumps({"status": "NO_EVENT", "items": []}).encode())})
    news_t = FakeTransport({"/news": (200, json.dumps({"status": "NO_EVENT", "articles": []}).encode())})
    llm_t = FakeTransport({"/chat/completions": (200, _llm_payload())})
    service = build_live_observation_service(
        now_fn=lambda: AS_OF,
        market=LiveMarketDataCollector(client=_client("market", "https://md.example", market_t)),
        disclosure=LiveDisclosureCollector(
            client=_client("dart", "https://example.test/api", dart_t, "DART_API_KEY"),
            received_at_fn=lambda: AS_OF,
        ),
        macro=LiveMacroCollector(
            client=_client("macro", "https://macro.example", macro_t),
            received_at_fn=lambda: AS_OF,
        ),
        news=LiveNewsCollector(
            client=_client("news", "https://news.example", news_t),
            received_at_fn=lambda: AS_OF,
        ),
    )
    service.llm = LiveLlmProvider(client=_client("llm", "https://llm.example/v1", llm_t, "LLM_API_KEY"))
    return service


def test_scheduled_use_fixture_unset_does_not_mix_fixture(monkeypatch):
    service = _live_service(monkeypatch, None)
    assert isinstance(service.scheduled, UnconfiguredScheduledEventCollector)
    assert not isinstance(service.scheduled, FixtureScheduledEventCollector)
    scheduled = service.scheduled.collect(AS_OF, ticker="005930")
    assert scheduled.status is CollectionStatus.DATA_UNAVAILABLE
    assert scheduled.status is not CollectionStatus.NO_EVENT
    assert "NOT_CONFIGURED" in (scheduled.error or "")
    assert scheduled.items == []


def test_scheduled_use_fixture_zero_does_not_leave_fixture(monkeypatch):
    service = _live_service(monkeypatch, "0")
    assert service.scheduled.__class__.__name__ == "UnconfiguredScheduledEventCollector"
    result = service.evaluate("005930", as_of=AS_OF)
    scheduled_status = next(
        item for item in result.provider_health if item.name == "scheduledEvent"
    )
    assert scheduled_status.status is CollectionStatus.DATA_UNAVAILABLE
    assert scheduled_status.required is False
    assert scheduled_status.error_code == "NOT_CONFIGURED"


def test_scheduled_use_fixture_one_still_refuses_fixture_rows(monkeypatch):
    service = _live_service(monkeypatch, "1")
    assert isinstance(service.scheduled, UnconfiguredScheduledEventCollector)
    fixture = FixtureScheduledEventCollector.from_file()
    fixture_rows = fixture.collect(AS_OF, ticker="005930")
    live_rows = service.scheduled.collect(AS_OF, ticker="005930")
    assert live_rows.items == []
    if fixture_rows.items:
        assert live_rows.items != fixture_rows.items
    result = service.evaluate("005930", as_of=AS_OF)
    assert result.data_mode is DataMode.LIVE_OBSERVATION
    assert result.readiness is not None
    # Optional unconfigured calendar must not be the sole BUY block.
    scheduled_only_block = [
        item
        for item in result.readiness.providers
        if item.name == "scheduledEvent" and item.required
    ]
    assert scheduled_only_block == []


def test_health_reports_scheduled_not_configured(monkeypatch):
    from ai_investment_agent.health.report import collect_health

    service = _live_service(monkeypatch, "1")
    report = collect_health(service)
    assert report.scheduled_health is not None
    assert report.scheduled_health.name == "ScheduledHealth"
    assert "NOT_CONFIGURED" in report.scheduled_health.detail
    assert "NO_EVENT" not in report.scheduled_health.detail or "not NO_EVENT" in report.scheduled_health.detail
