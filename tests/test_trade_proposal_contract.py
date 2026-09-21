from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.api.app import create_app
from ai_investment_agent.contracts.compatibility import (
    POLICY,
    parse_consumer_envelope,
    parse_producer_envelope,
)
from ai_investment_agent.contracts.encode import envelope_from_proposal
from ai_investment_agent.contracts.schema_loader import load_schema
from ai_investment_agent.contracts.versioning import (
    CURRENT_SCHEMA_VERSION,
    is_supported_schema,
)
from ai_investment_agent.domain.enums import Action, ConfidenceSource, Horizon
from ai_investment_agent.domain.envelope import TradeProposalEnvelope
from ai_investment_agent.domain.errors import SerializationError
from ai_investment_agent.domain.serialization import to_json
from tests.policy_support import buy_proposal
from tests.test_serialization import _proposal

REQUIRED_WIRE_FIELDS = {
    "schemaVersion",
    "proposalId",
    "generatedAt",
    "ticker",
    "market",
    "horizon",
    "action",
    "confidence",
    "expectedReturn",
    "estimatedRisk",
    "suggestedCapitalPct",
    "thesis",
    "invalidationConditions",
    "reasonCodes",
    "modelVersion",
    "featureVersion",
    "policyVersion",
}


def test_envelope_maps_minimum_contract_fields():
    proposal = _proposal()
    envelope = envelope_from_proposal(proposal)
    payload = envelope.model_dump(mode="json")
    assert REQUIRED_WIRE_FIELDS.issubset(payload)
    assert payload["schemaVersion"] == "ai.trade-proposal.v1"
    assert payload["proposalId"] == proposal.decision_id
    assert envelope.idempotency_key == proposal.decision_id
    assert payload["ticker"] == "005930"
    assert payload["market"] == "KRX"
    assert payload["horizon"] == "LONG_TERM"
    assert payload["action"] == "BUY"
    assert payload["confidence"] == 0.7
    assert payload["confidenceSource"] == "CALIBRATED"
    assert payload["suggestedCapitalPct"] == "5"
    assert payload["isOrder"] is False
    assert payload["artifactType"] == "TRADE_PROPOSAL"
    assert "quantity" not in payload
    assert "brokerOrderId" not in payload
    assert "accountId" not in payload


def test_raw_confidence_is_used_when_calibration_is_missing():
    proposal = _proposal().model_copy(update={"calibrated_confidence": None, "raw_confidence": 0.41})
    envelope = envelope_from_proposal(proposal)
    assert envelope.confidence == 0.41
    assert envelope.confidence_source is ConfidenceSource.RAW


def test_unknown_schema_version_is_rejected():
    assert is_supported_schema("ai.trade-proposal.v1") is True
    assert is_supported_schema("ai.trade-proposal.v2") is False
    raw = to_json(envelope_from_proposal(_proposal()))
    broken = raw.replace("ai.trade-proposal.v1", "ai.trade-proposal.v2")
    with pytest.raises((ValidationError, SerializationError)):
        parse_producer_envelope(broken)
    with pytest.raises((ValidationError, SerializationError)):
        parse_consumer_envelope(broken)


def test_producer_forbids_unknown_fields_consumer_ignores_additions():
    envelope = envelope_from_proposal(_proposal())
    payload = envelope.model_dump(mode="json")
    payload["traceId"] = "additive-future-field"
    raw = json.dumps(payload)
    with pytest.raises(SerializationError):
        parse_producer_envelope(raw)
    consumer = parse_consumer_envelope(raw)
    assert consumer.proposal_id == envelope.proposal_id
    assert not hasattr(consumer, "trace_id") or getattr(consumer, "trace_id", None) is None


def test_envelope_cannot_be_an_order():
    envelope = envelope_from_proposal(_proposal())
    payload = envelope.model_dump(by_alias=False)
    payload["is_order"] = True
    with pytest.raises(ValidationError):
        TradeProposalEnvelope.model_validate(payload)
    names = {
        name
        for name in dir(TradeProposalEnvelope)
        if callable(getattr(TradeProposalEnvelope, name, None))
    }
    assert names.isdisjoint({"to_order", "to_broker", "place_order", "submit_order"})


def test_json_schema_document_matches_v1_identity():
    schema = load_schema()
    assert schema["properties"]["schemaVersion"]["const"] == CURRENT_SCHEMA_VERSION
    assert schema["properties"]["isOrder"]["const"] is False
    assert REQUIRED_WIRE_FIELDS.issubset(set(schema["required"]))
    assert schema["additionalProperties"] is False


def test_compatibility_policy_does_not_connect_trading():
    dumped = POLICY.model_dump(mode="json")
    assert dumped["autoTradingSystemConnected"] is False
    assert dumped["liveOrderPathDefined"] is False
    assert dumped["idempotencyKey"] == "proposalId"
    assert dumped["unknownSchemaRejected"] is True
    assert dumped["currentSchema"] == "ai.trade-proposal.v1"


def test_contract_package_has_no_live_integration_imports():
    root = Path("src/ai_investment_agent/contracts")
    joined = "\n".join(path.read_text() for path in root.rglob("*.py"))
    for needle in ("import kafka", "import redis", "import kis", "from kis", "from redis", "from kafka"):
        assert needle not in joined
    for needle in ("def publish_to_ats", "def submit_order", "def place_order"):
        assert needle not in joined


def test_no_trade_envelope_keeps_zero_capital():
    proposal = buy_proposal(pct=0).model_copy(
        update={
            "action": Action.NO_TRADE,
            "horizon": Horizon.NONE,
            "expected_holding_period": 0,
            "suggested_capital_pct": 0,
        }
    )
    envelope = envelope_from_proposal(proposal)
    assert envelope.action is Action.NO_TRADE
    assert envelope.suggested_capital_pct == 0
    assert envelope.is_order is False


def test_analysis_api_exposes_contract_without_connecting():
    client = TestClient(create_app(AnalysisService()))
    root = client.get("/")
    assert root.json()["autoTradingSystemConnected"] is False
    assert root.json()["integrationStatus"] == "contract_only"
    assert root.json()["contractSchemaVersion"] == "ai.trade-proposal.v1"

    catalog = client.get("/contracts")
    assert catalog.status_code == 200
    assert catalog.json()["liveOrderPathDefined"] is False
    assert "ai.trade-proposal.v1" in catalog.json()["supported"]

    schema = client.get("/contracts/trade-proposal/v1")
    assert schema.status_code == 200
    assert schema.json()["properties"]["schemaVersion"]["const"] == "ai.trade-proposal.v1"

    policy = client.get("/contracts/compatibility")
    assert policy.json()["producerRole"] == "TradeProposal Producer"
    assert policy.json()["consumerRole"] == "TradeProposal Consumer"
    assert policy.json()["autoTradingSystemConnected"] is False

    evaluated = client.post("/analysis/evaluate", json={"ticker": "005930"})
    body = evaluated.json()
    assert body["ordersPlaced"] == 0
    assert body["envelope"]["schemaVersion"] == "ai.trade-proposal.v1"
    assert body["envelope"]["isOrder"] is False
    decision_id = body["decisionId"]
    fetched = client.get(f"/decisions/{decision_id}/envelope")
    assert fetched.status_code == 200
    assert fetched.json()["proposalId"] == decision_id
    assert fetched.json()["isOrder"] is False
    assert client.post("/contracts").status_code == 405
