"""Health endpoints must not probe collectors or mutate diagnostics/circuit."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ai_investment_agent.adapters.live.dart import LiveDisclosureCollector
from ai_investment_agent.adapters.live.factory import build_live_observation_service
from ai_investment_agent.adapters.live.llm import LiveLlmProvider
from ai_investment_agent.adapters.live.macro import LiveMacroCollector
from ai_investment_agent.adapters.live.market import LiveMarketDataCollector
from ai_investment_agent.adapters.live.news import LiveNewsCollector
from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.api.app import create_app
from ai_investment_agent.domain.enums import ModelHealthStatus
from ai_investment_agent.health.report import collect_health
from tests.test_live_acceptance_1058 import _dart_row
from tests.test_live_observation import FakeTransport, _client, _llm_payload, _market_payload

T0_ISO_PREFIX = "2026-09-21"


def _circuit_snap(collector: object) -> tuple[object, object, object]:
    client = getattr(collector, "_client", None)
    if client is None:
        return None, None, None
    circuit = client.circuit
    return circuit.failures, circuit.opened_at, client.last_attempt_count


def _diag_snap(collector: object) -> object:
    return getattr(collector, "last_diagnostics", None)


def _live_service(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-xxxxxxxxxxxx")
    market_t = FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())})
    dart_t = FakeTransport(
        {"/list.json": (200, json.dumps({"status": "000", "list": [_dart_row()]}).encode())}
    )
    macro_t = FakeTransport({"/macro": (200, json.dumps({"status": "NO_EVENT", "items": []}).encode())})
    news_t = FakeTransport({"/news": (200, json.dumps({"status": "NO_EVENT", "articles": []}).encode())})
    llm_t = FakeTransport({"/chat/completions": (200, _llm_payload())})
    service = build_live_observation_service(
        market=LiveMarketDataCollector(client=_client("market", "https://md.example", market_t)),
        disclosure=LiveDisclosureCollector(
            client=_client("dart", "https://example.test/api", dart_t, "DART_API_KEY"),
        ),
        macro=LiveMacroCollector(client=_client("macro", "https://macro.example", macro_t)),
        news=LiveNewsCollector(client=_client("news", "https://news.example", news_t)),
    )
    service.llm = LiveLlmProvider(
        client=_client("llm", "https://llm.example/v1", llm_t, "LLM_API_KEY")
    )
    return service, [market_t, dart_t, macro_t, news_t, llm_t]


def test_health_endpoints_do_not_call_transport_when_unobserved(monkeypatch):
    service, transports = _live_service(monkeypatch)
    client = TestClient(create_app(service))
    first = client.get("/health")
    second = client.get("/health")
    providers = client.get("/providers/health")
    again = client.get("/providers/health")
    assert first.status_code == 200
    assert second.status_code == 200
    assert providers.status_code == 200
    assert again.status_code == 200
    assert all(item.calls == [] for item in transports)
    body = first.json()
    assert body["unknownIsHealthy"] is False
    assert body["ordersEnabled"] is False
    assert body["brokerConnected"] is False
    assert body["autoTradingSystemConnected"] is False
    assert body["observationOnly"] is True
    assert body["probesOnRead"] is False
    assert body["scopedToDecisionId"] is None
    names = {item["name"] for item in body["components"]}
    assert names == {
        "MarketDataHealth",
        "DisclosureHealth",
        "MacroHealth",
        "NewsHealth",
        "ScheduledHealth",
        "LlmHealth",
        "ExternalDataHealth",
        "ModelHealth",
        "DatabaseHealth",
        "PersistenceHealth",
        "EventPipelineHealth",
    }
    assert body["marketDataHealth"]["status"] == "UNKNOWN"
    assert body["newsHealth"]["status"] == "UNKNOWN"
    assert body["disclosureHealth"]["status"] == "UNKNOWN"
    assert body["macroHealth"]["status"] == "UNKNOWN"
    assert body["llmHealth"]["status"] == "UNKNOWN"
    assert "NOT_CONFIGURED" in body["scheduledHealth"]["detail"]
    assert body["status"] != "HEALTHY"
    provider_body = providers.json()
    assert provider_body["unknownIsHealthy"] is False
    assert provider_body["observationOnly"] is True
    assert provider_body["probesOnRead"] is False


def test_health_lookup_does_not_mutate_diagnostics_or_circuit(monkeypatch):
    service, transports = _live_service(monkeypatch)
    service.evaluate("005930")
    calls_after_eval = [list(item.calls) for item in transports]
    snaps = {
        "market": (_circuit_snap(service.market), _diag_snap(service.market)),
        "news": (_circuit_snap(service.news), _diag_snap(service.news)),
        "disclosure": (_circuit_snap(service.disclosure), _diag_snap(service.disclosure)),
        "macro": (_circuit_snap(service.macro), _diag_snap(service.macro)),
        "llm": (_circuit_snap(service.llm), _diag_snap(service.llm)),
    }
    last_market = service.last_market
    last_external = service.last_external
    last_readiness = service.last_readiness
    client = TestClient(create_app(service))
    client.get("/health")
    client.get("/health")
    client.get("/providers/health")
    client.get("/providers/health")
    assert [item.calls for item in transports] == calls_after_eval
    assert (_circuit_snap(service.market), _diag_snap(service.market)) == snaps["market"]
    assert (_circuit_snap(service.news), _diag_snap(service.news)) == snaps["news"]
    assert (_circuit_snap(service.disclosure), _diag_snap(service.disclosure)) == snaps["disclosure"]
    assert (_circuit_snap(service.macro), _diag_snap(service.macro)) == snaps["macro"]
    assert (_circuit_snap(service.llm), _diag_snap(service.llm)) == snaps["llm"]
    assert service.last_market is last_market
    assert service.last_external is last_external
    assert service.last_readiness is last_readiness
    report = collect_health(service)
    assert report.market_data_health.status is not ModelHealthStatus.UNKNOWN
    assert report.observation_only is True
    assert report.scoped_to_decision_id is None
    assert "process last" in report.event_pipeline_health.detail


def test_unobserved_fixture_health_is_not_treated_as_connected():
    service = AnalysisService()
    report = collect_health(service)
    assert report.market_data_health.status is ModelHealthStatus.UNKNOWN
    assert report.news_health is not None
    assert report.news_health.status is ModelHealthStatus.UNKNOWN
    assert report.disclosure_health is not None
    assert report.disclosure_health.status is ModelHealthStatus.UNKNOWN
    assert report.llm_health is not None
    assert report.llm_health.status is ModelHealthStatus.UNKNOWN
    assert report.status is not ModelHealthStatus.HEALTHY
    assert report.unknown_treated_as_healthy is False
    client = TestClient(create_app(service))
    payload = client.get("/health").json()
    assert payload["unknownIsHealthy"] is False
    assert payload["ordersEnabled"] is False
    assert payload["brokerConnected"] is False
    assert payload["autoTradingSystemConnected"] is False
    assert payload["marketDataHealth"]["status"] == "UNKNOWN"
