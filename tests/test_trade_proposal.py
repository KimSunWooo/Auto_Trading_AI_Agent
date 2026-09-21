from decimal import Decimal

from ai_investment_agent.agents.judgment_agent import JudgmentRequest
from ai_investment_agent.domain.enums import Action, DecisionType, Horizon
from tests.support import make_agent, provided_capital


def test_trade_proposal_generation_for_known_market():
    agent, repository, publisher = make_agent("known_market.json")
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )
    proposal = snapshot.proposal

    assert proposal.ticker == "005930"
    assert proposal.decision_id.startswith("dec_")
    assert proposal.action is Action.BUY
    assert proposal.horizon is Horizon.LONG_TERM
    assert proposal.decision is DecisionType.LONG_TERM_BUY
    assert 0 < proposal.raw_confidence <= 1
    assert 0 < proposal.calibrated_confidence <= 1
    assert proposal.suggested_capital_pct == Decimal("5")
    assert proposal.suggested_capital_pct <= Decimal("100")
    assert proposal.expected_holding_period == 252
    assert proposal.thesis.headline
    assert proposal.invalidation_conditions
    assert proposal.market_regime.regime.value == "SIDEWAYS"
    assert proposal.model_version
    assert proposal.feature_version
    assert proposal.policy_version
    assert proposal.generated_at
    assert snapshot.proposal.decision_id == snapshot.decision_id
    assert repository.get_snapshot(snapshot.decision_id) is not None
    assert len(publisher.published) == 1
    stages = [entry.stage.value for entry in repository.list_journal(snapshot.decision_id)]
    assert stages == ["DATA", "DATA", "ANALYSIS", "RISK_ASSESSMENT", "DECISION", "TRADE_PROPOSAL"]
