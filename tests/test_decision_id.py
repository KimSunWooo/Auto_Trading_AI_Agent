from ai_investment_agent.agents.judgment_agent import JudgmentRequest
from ai_investment_agent.domain.ids import is_decision_id
from tests.support import make_agent, provided_capital


def test_decision_id_is_generated_and_unique():
    agent, _, _ = make_agent("known_market.json")
    first = agent.judge(JudgmentRequest(ticker="005930", capital_context=provided_capital()))
    second = agent.judge(JudgmentRequest(ticker="005930", capital_context=provided_capital()))

    assert is_decision_id(first.decision_id)
    assert is_decision_id(second.decision_id)
    assert first.decision_id != second.decision_id
    assert first.proposal.decision_id == first.decision_id
    assert second.proposal.decision_id == second.decision_id
    assert first.decision_id.startswith("dec_")
    assert len(first.decision_id) == 36
