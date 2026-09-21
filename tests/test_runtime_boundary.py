from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from ai_investment_agent.adapters.fixtures.portfolio import fixture_capital
from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.api.app import create_app
from ai_investment_agent.contracts.compatibility import parse_producer_envelope
from ai_investment_agent.contracts.encode import envelope_from_proposal
from ai_investment_agent.domain.enums import DataMode, Horizon
from ai_investment_agent.domain.envelope import TradeProposalEnvelope
from ai_investment_agent.domain.fingerprint import context_fingerprint
from ai_investment_agent.policy.freshness import ProposalFreshnessPolicy
from fastapi.testclient import TestClient
from ai_investment_agent.replay.service import ReplayService
from tests.horizon_support import (
    AS_OF,
    bullish_long,
    good_entry,
    judge,
    make_investment_agent,
    make_regime,
    make_snapshot,
    weak_short,
)
from ai_investment_agent.agents.investment_agent import InvestmentJudgmentRequest
from tests.support import provided_capital
from tests.test_serialization import _proposal


def test_fixture_proposal_has_data_mode_fixture():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
    )
    assert snapshot.proposal.data_mode is DataMode.FIXTURE
    assert snapshot.data_mode is DataMode.FIXTURE
    envelope = envelope_from_proposal(snapshot.proposal)
    assert envelope.data_mode is DataMode.FIXTURE
    assert envelope.schema_version == "ai.trade-proposal.v1"


def test_replay_proposal_identifies_replay():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
        data_mode=DataMode.REPLAY,
    )
    assert snapshot.proposal.data_mode is DataMode.REPLAY
    assert snapshot.data_mode is DataMode.REPLAY
    envelope = envelope_from_proposal(snapshot.proposal)
    assert envelope.data_mode is DataMode.REPLAY
    agent, repository = make_investment_agent()
    stored = agent.judge(
        InvestmentJudgmentRequest(
            ticker="005930",
            snapshot=make_snapshot(),
            regime=make_regime(),
            long_features=bullish_long(),
            short_features=weak_short(),
            capital_context=provided_capital(),
            entry=good_entry(),
            data_mode=DataMode.REPLAY,
        )
    )
    bundle = ReplayService(repository).replay(stored.decision_id)
    assert bundle.data_mode is DataMode.REPLAY


def test_analysis_as_of_is_separated_from_generated_at():
    analysis_time = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    generated = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
    agent, _ = make_investment_agent()
    agent._now = lambda: generated
    snapshot = agent.judge(
        InvestmentJudgmentRequest(
            ticker="005930",
            snapshot=make_snapshot().model_copy(update={"as_of": analysis_time}),
            regime=make_regime(),
            long_features=bullish_long(),
            short_features=weak_short(),
            capital_context=provided_capital(),
            entry=good_entry(),
        )
    )
    assert snapshot.proposal.analysis_as_of == analysis_time
    assert snapshot.proposal.generated_at == generated
    assert snapshot.proposal.analysis_as_of != snapshot.proposal.generated_at
    assert snapshot.proposal.valid_until >= snapshot.proposal.generated_at
    ttl = ProposalFreshnessPolicy().ttl_for(snapshot.proposal.horizon)
    assert snapshot.proposal.valid_until == generated + ttl


def test_context_fingerprint_is_deterministic():
    first = context_fingerprint(
        ticker="005930",
        analysis_as_of=AS_OF,
        event_ids=["evt_2", "evt_1"],
        last_price="71000",
        data_mode=DataMode.FIXTURE,
    )
    second = context_fingerprint(
        ticker="005930",
        analysis_as_of=AS_OF,
        event_ids=["evt_1", "evt_2"],
        last_price="71000",
        data_mode=DataMode.FIXTURE,
    )
    changed = context_fingerprint(
        ticker="005930",
        analysis_as_of=AS_OF,
        event_ids=["evt_1", "evt_3"],
        last_price="71000",
        data_mode=DataMode.FIXTURE,
    )
    assert first == second
    assert first.startswith("cfp_")
    assert first != changed


def test_same_judgment_context_keeps_fingerprint():
    first = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
    )
    second = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
    )
    assert first.context_fingerprint == second.context_fingerprint
    assert first.proposal.context_fingerprint == first.context_fingerprint


def test_envelope_is_still_not_an_order_and_keeps_v1():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
    )
    envelope = envelope_from_proposal(snapshot.proposal)
    assert envelope.is_order is False
    assert envelope.artifact_type == "TRADE_PROPOSAL"
    payload = envelope.model_dump(by_alias=False)
    payload["is_order"] = True
    try:
        TradeProposalEnvelope.model_validate(payload)
        raised = False
    except ValidationError:
        raised = True
    assert raised
    dumped = envelope.model_dump(mode="json")
    assert dumped["schemaVersion"] == "ai.trade-proposal.v1"
    assert "quantity" not in dumped
    assert "accountId" not in dumped
    assert "brokerOrderId" not in dumped


def test_unknown_schema_version_still_rejected():
    raw = envelope_from_proposal(_proposal()).model_dump_json()
    broken = raw.replace("ai.trade-proposal.v1", "ai.trade-proposal.v2")
    try:
        parse_producer_envelope(broken)
        rejected = False
    except Exception:
        rejected = True
    assert rejected


def test_api_exposes_runtime_and_data_mode():
    client = TestClient(create_app(AnalysisService()))
    root = client.get("/").json()
    assert root["runtimeProfile"] == "FIXTURE"
    assert root["dataMode"] == "FIXTURE"
    assert root["ordersEnabled"] is False
    assert root["brokerConnected"] is False
    assert root["autoTradingSystemConnected"] is False
    health = client.get("/health").json()
    assert health["runtimeProfile"] == "FIXTURE"
    assert health["dataMode"] == "FIXTURE"
    assert health["ordersEnabled"] is False


def test_fixture_evaluate_envelope_tracks_data_mode():
    result = AnalysisService().evaluate("005930", capital_context=fixture_capital())
    assert result.data_mode is DataMode.FIXTURE
    assert result.envelope is not None
    assert result.envelope.data_mode is DataMode.FIXTURE
    assert result.envelope.is_order is False
    assert result.snapshot.proposal.valid_until is not None
    assert result.snapshot.proposal.analysis_as_of is not None


def test_short_horizon_ttl_is_shorter_than_long():
    policy = ProposalFreshnessPolicy()
    assert policy.ttl_for(Horizon.SHORT_TERM) < policy.ttl_for(Horizon.LONG_TERM)
    now = AS_OF
    assert policy.valid_until(generated_at=now, horizon=Horizon.SHORT_TERM) == now + timedelta(
        hours=4
    )
