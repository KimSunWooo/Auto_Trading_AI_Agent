from fastapi.testclient import TestClient

from ai_investment_agent.analysis.service import PIPELINE_STAGES, AnalysisService
from ai_investment_agent.api.app import FORBIDDEN_ORDER_PATHS, create_app
from ai_investment_agent.domain.enums import ModelHealthStatus
from ai_investment_agent.health.report import aggregate_status, collect_health


def test_evaluate_pipeline_reaches_journal_without_orders():
    service = AnalysisService()
    result = service.evaluate("005930")
    assert result.orders_placed == 0
    assert result.broker_called is False
    assert result.pipeline == list(PIPELINE_STAGES)
    assert result.decision_id.startswith("dec_")
    assert result.record.ticker == "005930"
    assert result.record.action.value in {
        "BUY",
        "SELL",
        "HOLD",
        "NO_TRADE",
        "TACTICAL_WAIT",
        "EXIT_REVIEW",
    }
    stored = service.get_decision(result.decision_id)
    assert stored is not None
    assert stored.proposal.decision_id == result.decision_id
    replayed = service.replay_decision(result.decision_id)
    assert replayed.versions.model_version == stored.proposal.model_version
    assert replayed.record.action == result.record.action
    assert len(service.publisher.published) == 1


def test_analysis_api_evaluate_list_get_replay_and_health():
    client = TestClient(create_app(AnalysisService()))
    evaluated = client.post("/analysis/evaluate", json={"ticker": "005930"})
    assert evaluated.status_code == 200
    body = evaluated.json()
    assert body["ordersPlaced"] == 0
    assert body["brokerCalled"] is False
    assert body["pipeline"] == list(PIPELINE_STAGES)
    decision_id = body["decisionId"]

    listed = client.get("/decisions")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["decisionId"] == decision_id

    fetched = client.get(f"/decisions/{decision_id}")
    assert fetched.status_code == 200
    assert fetched.json()["ticker"] == "005930"

    replayed = client.post(f"/decisions/{decision_id}/replay")
    assert replayed.status_code == 200
    assert replayed.json()["decisionId"] == decision_id
    assert replayed.json()["versions"]["policyVersion"]
    assert replayed.json()["deterministicRerun"] is False

    missing = client.get("/decisions/dec_" + "0" * 32)
    assert missing.status_code == 404

    health = client.get("/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["unknownIsHealthy"] is False
    assert payload["ordersEnabled"] is False
    assert payload["brokerConnected"] is False
    assert payload["autoTradingSystemConnected"] is False
    names = {item["name"] for item in payload["components"]}
    assert names == {
        "MarketDataHealth",
        "ExternalDataHealth",
        "ModelHealth",
        "DatabaseHealth",
        "EventPipelineHealth",
    }
    assert payload["status"] in {"HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"}
    if payload["status"] == "UNKNOWN":
        assert payload["modelHealthTreatedAsHealthy"] is False
    assert payload["marketDataHealth"]["name"] == "MarketDataHealth"
    root = client.get("/")
    assert root.json()["ordersEnabled"] is False


def test_order_and_broker_routes_do_not_exist():
    client = TestClient(create_app(AnalysisService()))
    for path in FORBIDDEN_ORDER_PATHS + ("/broker/kis", "/orders/new"):
        assert client.post(path).status_code == 404
        assert client.get(path).status_code == 404
    documented = {route.path for route in client.app.routes}
    for needle in ("/orders", "/buy", "/sell", "/cancel", "/broker"):
        assert not any(needle == path or path.startswith(needle + "/") for path in documented)


def test_unknown_component_keeps_overall_health_unknown():
    assert aggregate_status([]) is ModelHealthStatus.UNKNOWN
    assert (
        aggregate_status([ModelHealthStatus.HEALTHY, ModelHealthStatus.UNKNOWN])
        is ModelHealthStatus.UNKNOWN
    )
    assert aggregate_status([ModelHealthStatus.UNKNOWN]) is not ModelHealthStatus.HEALTHY
    assert (
        aggregate_status([ModelHealthStatus.UNHEALTHY, ModelHealthStatus.UNKNOWN])
        is ModelHealthStatus.UNHEALTHY
    )
    service = AnalysisService()
    report = collect_health(service)
    assert report.unknown_treated_as_healthy is False
    assert report.model_health.status is ModelHealthStatus.UNKNOWN
    assert report.status is not ModelHealthStatus.HEALTHY
    assert report.treated_as_healthy is False
    assert report.orders_enabled is False
