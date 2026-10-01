"""10.5.8 Live default clock and as_of / receive / generated_at separation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ai_investment_agent.adapters.live.dart import LiveDisclosureCollector
from ai_investment_agent.adapters.live.factory import build_live_observation_service
from ai_investment_agent.adapters.live.llm import LiveLlmProvider
from ai_investment_agent.adapters.live.macro import LiveMacroCollector
from ai_investment_agent.adapters.live.market import LiveMarketDataCollector
from ai_investment_agent.adapters.live.news import LiveNewsCollector
from ai_investment_agent.analysis.clock import FIXTURE_AS_OF, utc_now
from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.api.app import _default_service, create_app
from ai_investment_agent.domain.enums import DataMode
from ai_investment_agent.domain.runtime import RuntimeSettings
from tests.test_live_observation import (
    FakeTransport,
    _client,
    _llm_payload,
    _market_payload,
)


def test_fixture_service_keeps_pinned_clock():
    service = AnalysisService()
    assert service._now() == FIXTURE_AS_OF
    result = service.evaluate("005930")
    assert result.snapshot.analysis_as_of == FIXTURE_AS_OF


def test_live_factory_default_clock_is_timezone_aware_utc():
    service = build_live_observation_service()
    moment = service._now()
    assert moment.tzinfo is not None
    assert abs((moment - utc_now()).total_seconds()) < 5
    assert moment != FIXTURE_AS_OF


def test_api_default_live_path_omitted_as_of_uses_current_utc(monkeypatch):
    monkeypatch.setenv("AI_DATA_MODE", "LIVE_OBSERVATION")
    service = _default_service()
    assert service.runtime.data_mode is DataMode.LIVE_OBSERVATION
    assert service._now() != FIXTURE_AS_OF
    assert service._now().tzinfo is not None


def test_omitted_as_of_on_live_evaluate_uses_injected_now(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-xxxxxxxxxxxx")
    frozen = datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)
    market_t = FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())})
    dart_t = FakeTransport({"/list.json": (200, json.dumps({"status": "013", "list": []}).encode())})
    macro_t = FakeTransport({"/macro": (200, json.dumps({"status": "NO_EVENT", "items": []}).encode())})
    news_t = FakeTransport({"/news": (200, json.dumps({"status": "NO_EVENT", "articles": []}).encode())})
    llm_t = FakeTransport({"/chat/completions": (200, _llm_payload())})
    service = build_live_observation_service(
        now_fn=lambda: frozen,
        market=LiveMarketDataCollector(client=_client("market", "https://md.example", market_t)),
        disclosure=LiveDisclosureCollector(
            client=_client("dart", "https://example.test/api", dart_t, "DART_API_KEY"),
            received_at_fn=lambda: frozen,
        ),
        macro=LiveMacroCollector(
            client=_client("macro", "https://macro.example", macro_t),
            received_at_fn=lambda: frozen,
        ),
        news=LiveNewsCollector(
            client=_client("news", "https://news.example", news_t),
            received_at_fn=lambda: frozen,
        ),
    )
    service.llm = LiveLlmProvider(client=_client("llm", "https://llm.example/v1", llm_t, "LLM_API_KEY"))
    result = service.evaluate("005930")
    assert result.snapshot.analysis_as_of == frozen
    assert result.snapshot.analysis_as_of != FIXTURE_AS_OF
    assert result.snapshot.created_at == frozen
    assert result.snapshot.proposal.generated_at == frozen


def test_historical_as_of_does_not_backdate_receive_time(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    receive = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
    as_of = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
    payload = {
        "status": "000",
        "list": [
            {
                "corp_name": "삼성전자",
                "corp_code": "00126380",
                "stock_code": "005930",
                "report_nm": "당일공시",
                "rcept_no": "20260921008888",
                "rcept_dt": "20260921",
            }
        ],
    }
    collector = LiveDisclosureCollector(
        client=_client(
            "dart",
            "https://example.test/api",
            FakeTransport({"/list.json": (200, json.dumps(payload).encode())}),
            "DART_API_KEY",
        ),
        received_at_fn=lambda: receive,
    )
    result = collector.collect("005930", as_of)
    assert result.items == []
    afternoon = collector.collect("005930", receive)
    assert afternoon.items
    assert afternoon.items[0].timestamps.source_received_at == receive
    assert afternoon.items[0].timestamps.tradable_at == receive
    assert afternoon.items[0].timestamps.published_at == datetime(
        2026, 9, 21, tzinfo=timezone.utc
    )


def test_live_api_omitted_as_of_does_not_use_fixture_date(monkeypatch):
    monkeypatch.setenv("AI_DATA_MODE", "LIVE_OBSERVATION")
    frozen = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    service = AnalysisService(
        now_fn=lambda: frozen,
        runtime=RuntimeSettings(data_mode=DataMode.LIVE_OBSERVATION),
    )
    client = TestClient(create_app(service))
    response = client.post("/analysis/evaluate", json={"ticker": "005930"})
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["analysisAsOf"].startswith("2026-10-01")
    assert not body["snapshot"]["analysisAsOf"].startswith("2026-09-21T09:00:00")


