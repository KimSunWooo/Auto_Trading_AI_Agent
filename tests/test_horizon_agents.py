from ai_investment_agent.domain.enums import (
    Action,
    DecisionType,
    HorizonChoice,
    MarketRegimeType,
    ReasonCode,
    Stance,
)
from tests.horizon_support import (
    bearish_short,
    bullish_long,
    high_cost_long,
    judge,
    poor_entry,
    weak_long,
    weak_short,
)


def test_long_positive_short_negative_is_tactical_wait():
    snapshot = judge(long_features=bullish_long(), short_features=bearish_short())
    proposal = snapshot.proposal
    decision = snapshot.horizon_decision

    assert decision is not None
    assert decision.choice is HorizonChoice.TACTICAL_WAIT
    assert decision.long_stance is Stance.BULLISH
    assert decision.short_stance is Stance.BEARISH
    assert ReasonCode.LONG_THESIS_VALID.value in proposal.reason_codes
    assert ReasonCode.LONG_SHORT_CONFLICT.value in proposal.reason_codes
    assert proposal.action is Action.TACTICAL_WAIT
    assert proposal.decision is DecisionType.TACTICAL_WAIT
    assert proposal.suggested_capital_pct == 0
    assert "earnings_recovery" in snapshot.thesis.drivers
    assert "sector_strength" in snapshot.thesis.drivers
    assert snapshot.thesis.invalidations


def test_both_agents_weak_is_no_trade():
    snapshot = judge(long_features=weak_long(), short_features=weak_short())
    assert snapshot.proposal.action is Action.NO_TRADE
    assert snapshot.horizon_decision.choice is HorizonChoice.NO_TRADE
    assert ReasonCode.BOTH_AGENTS_WEAK.value in snapshot.proposal.reason_codes
    assert ReasonCode.POLICY_NO_TRADE_IS_VALID.value in snapshot.proposal.reason_codes


def test_unknown_market_is_no_trade_even_if_long_is_bullish():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        regime=MarketRegimeType.UNKNOWN,
    )
    assert snapshot.proposal.action is Action.NO_TRADE
    assert snapshot.horizon_decision.choice is HorizonChoice.NO_TRADE
    assert ReasonCode.UNKNOWN_MARKET_REGIME.value in snapshot.proposal.reason_codes
    assert snapshot.horizon_decision.long_stance is Stance.BULLISH


def test_low_net_edge_is_no_trade():
    snapshot = judge(long_features=high_cost_long(), short_features=weak_short())
    assert snapshot.proposal.action is Action.NO_TRADE
    assert snapshot.horizon_decision.choice is HorizonChoice.NO_TRADE
    assert ReasonCode.LOW_NET_EDGE.value in snapshot.proposal.reason_codes


def test_long_thesis_with_poor_entry_waits_instead_of_buy_now():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=poor_entry(),
    )
    proposal = snapshot.proposal
    assert snapshot.horizon_decision.choice is HorizonChoice.TACTICAL_WAIT
    assert snapshot.horizon_decision.entry_timing.value == "WAIT"
    assert proposal.action is Action.TACTICAL_WAIT
    assert proposal.decision is not DecisionType.LONG_TERM_BUY
    assert ReasonCode.LONG_THESIS_VALID.value in proposal.reason_codes
    assert ReasonCode.POOR_ENTRY.value in proposal.reason_codes
    assert ReasonCode.ENTRY_WAIT.value in proposal.reason_codes
    assert "earnings_recovery" in snapshot.thesis.drivers
    assert "sector_breakdown" in snapshot.thesis.invalidations or snapshot.thesis.invalidations
