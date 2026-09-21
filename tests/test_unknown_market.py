from ai_investment_agent.agents.judgment_agent import JudgmentRequest
from ai_investment_agent.domain.enums import Action, DecisionType, ReasonCode
from tests.support import make_agent, provided_capital


def test_unknown_market_yields_no_trade():
    agent, repository, publisher = make_agent("unknown_market.json")
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )

    proposal = snapshot.proposal
    assert proposal.action is Action.NO_TRADE
    assert proposal.decision is DecisionType.NO_TRADE
    assert proposal.horizon.value == "NONE"
    assert proposal.suggested_capital_pct == 0
    assert ReasonCode.UNKNOWN_MARKET_REGIME.value in proposal.reason_codes
    assert ReasonCode.POLICY_NO_TRADE_IS_VALID.value in proposal.reason_codes
    assert snapshot.market_regime.regime.value == "UNKNOWN"
    assert repository.get_snapshot(proposal.decision_id) is snapshot
    assert publisher.published == [proposal]
    assert proposal.expected_holding_period is None
