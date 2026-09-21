from decimal import Decimal

from ai_investment_agent.agents.judgment_agent import JudgmentRequest
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import Action, DecisionType, ReasonCode
from tests.support import make_agent


def test_missing_capital_context_is_not_unlimited():
    agent, _, _ = make_agent("known_market.json", desired=DecisionType.LONG_TERM_BUY)
    snapshot = agent.judge(JudgmentRequest(ticker="005930", capital_context=None))

    capital = snapshot.capital_context
    assert capital.source == "missing_conservative_default"
    assert capital.total_capital == Decimal("0")
    assert capital.ai_capital_limit == Decimal("0")
    assert capital.ai_capital_ratio == Decimal("0")
    assert capital.long_term_budget == Decimal("0")
    assert capital.short_term_budget == Decimal("0")
    assert capital.reserve_cash == Decimal("0")
    assert capital.risk_budget == Decimal("0")
    assert capital.deployable_capital == Decimal("0")

    proposal = snapshot.proposal
    assert proposal.suggested_capital_pct == Decimal("0")
    assert proposal.suggested_capital_pct < Decimal("1")
    assert ReasonCode.CAPITAL_CONTEXT_MISSING.value in proposal.reason_codes
    assert proposal.action is Action.NO_TRADE
    assert proposal.decision is DecisionType.NO_TRADE


def test_missing_conservative_factory_is_zero_not_open_ended():
    capital = CapitalContext.missing_conservative()
    assert capital.was_provided is False
    assert capital.deployable_capital == 0
    dumped = capital.model_dump(by_alias=False)
    numeric = [
        dumped["total_capital"],
        dumped["ai_capital_limit"],
        dumped["long_term_budget"],
        dumped["short_term_budget"],
        dumped["reserve_cash"],
        dumped["risk_budget"],
    ]
    assert all(value == Decimal("0") for value in numeric)
