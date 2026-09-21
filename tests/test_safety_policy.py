from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_investment_agent.adapters.fixtures.portfolio import (
    fixture_human_override,
    fixture_portfolio,
)
from ai_investment_agent.domain.enums import (
    Action,
    DecisionType,
    KillSwitchLevel,
    PolicyAction,
    PolicyState,
    ReasonCode,
)
from ai_investment_agent.domain.policy import HumanOverride, PolicyResult
from tests.policy_support import apply, buy_proposal, sell_proposal
from tests.support import provided_capital


def test_ai_capital_overshoot_is_clamped_to_remaining_limit():
    proposal = buy_proposal(pct=Decimal("50"))
    result = apply(
        proposal,
        portfolio=fixture_portfolio(used_ai_capital=Decimal("8000000")),
    )
    policy = result.policy_result
    assert policy is not None
    assert policy.action is PolicyAction.CLAMP
    assert result.action is Action.BUY
    assert result.suggested_capital_pct == Decimal("20")
    assert result.suggested_capital_pct < policy.original_suggested_capital_pct
    assert ReasonCode.AI_CAPITAL_CLAMPED.value in result.reason_codes
    assert policy.force_sell_all is False
    # Total capital is 100M; AI may only use the 10M limit.
    notional = provided_capital().ai_capital_limit * result.suggested_capital_pct / 100
    assert fixture_portfolio(used_ai_capital=Decimal("8000000")).used_ai_capital + notional <= (
        provided_capital().ai_capital_limit
    )


def test_ai_capital_exhausted_rejects_new_buy():
    result = apply(
        buy_proposal(pct=Decimal("10")),
        portfolio=fixture_portfolio(used_ai_capital=Decimal("10000000")),
    )
    assert result.action is Action.NO_TRADE
    assert result.decision is DecisionType.NO_TRADE
    assert result.suggested_capital_pct == Decimal("0")
    assert result.policy_result.action is PolicyAction.REJECT
    assert ReasonCode.AI_CAPITAL_LIMIT_EXCEEDED.value in result.reason_codes


def test_unknown_policy_forbids_new_buy():
    result = apply(buy_proposal(), policy_state=PolicyState.UNKNOWN)
    assert result.action is not Action.BUY
    assert result.decision is not DecisionType.LONG_TERM_BUY
    assert result.suggested_capital_pct == Decimal("0")
    assert result.policy_result.action is PolicyAction.DEFER
    assert result.action is Action.TACTICAL_WAIT
    assert ReasonCode.POLICY_UNKNOWN_NO_NEW_BUY.value in result.reason_codes


def test_high_correlation_reduces_exposure():
    original = Decimal("20")
    result = apply(
        buy_proposal(pct=original),
        portfolio=fixture_portfolio(pairwise_correlation_max=Decimal("0.80")),
    )
    assert result.action is Action.BUY
    assert result.policy_result.action is PolicyAction.CLAMP
    assert result.suggested_capital_pct == Decimal("4.00")
    assert result.suggested_capital_pct < original
    assert ReasonCode.HIGH_CORRELATION_EXPOSURE_REDUCED.value in result.reason_codes


def test_human_symbol_blacklist_blocks_proposal():
    result = apply(
        buy_proposal(ticker="005930"),
        human=fixture_human_override(symbol_blacklist=("005930",)),
    )
    assert result.action is Action.NO_TRADE
    assert result.policy_result.action is PolicyAction.REJECT
    assert ReasonCode.HUMAN_SYMBOL_BLACKLIST.value in result.reason_codes


def test_human_sector_blacklist_blocks_proposal():
    result = apply(
        buy_proposal(),
        human=fixture_human_override(sector_blacklist=("SEMICONDUCTOR",)),
        portfolio=fixture_portfolio(proposal_sector="semiconductor"),
    )
    assert result.action is Action.NO_TRADE
    assert ReasonCode.HUMAN_SECTOR_BLACKLIST.value in result.reason_codes


def test_ai_disabled_is_no_trade():
    result = apply(buy_proposal(), human=fixture_human_override(ai_enabled=False))
    assert result.action is Action.NO_TRADE
    assert result.decision is DecisionType.NO_TRADE
    assert result.suggested_capital_pct == Decimal("0")
    assert result.policy_result.policy_state is PolicyState.AI_DISABLED
    assert result.policy_result.action is PolicyAction.REJECT
    assert ReasonCode.HUMAN_AI_DISABLED.value in result.reason_codes
    assert ReasonCode.POLICY_AI_DISABLED.value in result.reason_codes


def test_all_trading_disabled_is_not_force_sell_all():
    result = apply(
        sell_proposal(),
        kill_switch=KillSwitchLevel.LEVEL_4_ALL_TRADING_DISABLED,
    )
    assert result.action is Action.NO_TRADE
    assert result.action is not Action.SELL
    assert result.policy_result.force_sell_all is False
    assert result.policy_result.kill_switch_level is (
        KillSwitchLevel.LEVEL_4_ALL_TRADING_DISABLED
    )
    assert ReasonCode.POLICY_ALL_TRADING_DISABLED.value in result.reason_codes
    assert ReasonCode.POLICY_NOT_FORCE_SELL_ALL.value in result.reason_codes
    with pytest.raises(ValidationError):
        PolicyResult(
            policy_state=PolicyState.AI_DISABLED,
            kill_switch_level=KillSwitchLevel.LEVEL_4_ALL_TRADING_DISABLED,
            action=PolicyAction.REJECT,
            original_suggested_capital_pct=Decimal("0"),
            applied_suggested_capital_pct=Decimal("0"),
            force_sell_all=True,
        )


def test_human_override_is_frozen_against_ai_mutation():
    override = HumanOverride(ai_enabled=True, symbol_blacklist=("005930",))
    with pytest.raises(ValidationError):
        override.ai_enabled = False
    with pytest.raises(ValidationError):
        override.symbol_blacklist = ()
    still = apply(buy_proposal(), human=override)
    assert still.action is Action.NO_TRADE
