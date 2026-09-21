"""AI-side safety policy. Allows, clamps, defers, or rejects TradeProposals.

This layer is not a broker RiskManager. It does not halt a live trading
system, does not place orders, and never treats ALL_TRADING_DISABLED as
FORCE_SELL_ALL.
"""

from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import (
    Action,
    DataMode,
    Horizon,
    KillSwitchLevel,
    PolicyAction,
    PolicyState,
    ReasonCode,
)
from ai_investment_agent.domain.policy import (
    HumanOverride,
    PolicyResult,
    PortfolioContext,
    RiskBudgets,
)
from ai_investment_agent.domain.proposal import TradeProposal

CORRELATION_REDUCTION_THRESHOLD = Decimal("0.70")
STRESS_CORRELATION_THRESHOLD = Decimal("0.85")
REDUCED_EXPOSURE_SCALE = Decimal("0.50")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


class SafetyPolicyLayer:
    """Capital-preservation policy applied after judgment, before publish.

    HumanOverride is read-only. The layer has no method that writes it.
    """

    def apply(
        self,
        proposal: TradeProposal,
        *,
        capital: CapitalContext,
        portfolio: PortfolioContext | None = None,
        risk_budgets: RiskBudgets | None = None,
        human: HumanOverride | None = None,
        policy_state: PolicyState = PolicyState.NORMAL,
        kill_switch: KillSwitchLevel = KillSwitchLevel.LEVEL_0_NORMAL,
        data_mode: DataMode = DataMode.FIXTURE,
    ) -> TradeProposal:
        live_compatible = data_mode in {DataMode.LIVE_OBSERVATION, DataMode.LIVE_SHADOW}
        if live_compatible and (portfolio is None or risk_budgets is None):
            missing: list[str] = []
            if portfolio is None:
                missing.append(ReasonCode.PORTFOLIO_CONTEXT_MISSING.value)
            if risk_budgets is None:
                missing.append(ReasonCode.RISK_BUDGETS_MISSING.value)
            missing.append(ReasonCode.POLICY_UNKNOWN_NO_NEW_BUY.value)
            missing.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
            blocked = _as_wait(proposal) if proposal.action is Action.BUY else proposal
            result = PolicyResult(
                policy_state=PolicyState.UNKNOWN,
                kill_switch_level=kill_switch,
                action=PolicyAction.DEFER if proposal.action is Action.BUY else PolicyAction.ALLOW,
                original_suggested_capital_pct=proposal.suggested_capital_pct,
                applied_suggested_capital_pct=ZERO,
                reason_codes=_unique(list(proposal.reason_codes) + missing),
                force_sell_all=False,
                capital_remaining=ZERO,
                risk_remaining=ZERO,
            )
            return blocked.model_copy(
                update={
                    "reason_codes": result.reason_codes,
                    "policy_result": result,
                    "suggested_capital_pct": ZERO,
                    "action": blocked.action,
                    "horizon": blocked.horizon,
                }
            )
        book = portfolio if portfolio is not None else PortfolioContext.fixture_empty()
        if book.source != "fixture":
            raise ValueError("SafetyPolicyLayer accepts fixture PortfolioContext only")
        budgets = risk_budgets if risk_budgets is not None else RiskBudgets.fixture_open()
        override = human if human is not None else HumanOverride()
        original_pct = proposal.suggested_capital_pct
        remaining_capital = _remaining_ai_capital(capital, book)
        remaining_risk = min(
            budgets.per_position.remaining,
            budgets.daily_loss.remaining,
            budgets.ai_drawdown.remaining,
        )

        working = proposal
        reasons: list[str] = []
        action = PolicyAction.ALLOW
        pct = original_pct

        halt = _hard_halt(working, override, policy_state, kill_switch, book)
        if halt is not None:
            blocked_action, result_state, blocked_reasons = halt
            working = _as_no_trade(working) if blocked_action is PolicyAction.REJECT else _as_wait(
                working
            )
            result = PolicyResult(
                policy_state=result_state,
                kill_switch_level=kill_switch,
                action=blocked_action,
                original_suggested_capital_pct=original_pct,
                applied_suggested_capital_pct=ZERO,
                reason_codes=_unique(list(proposal.reason_codes) + blocked_reasons),
                force_sell_all=False,
                capital_remaining=remaining_capital,
                risk_remaining=remaining_risk,
            )
            return working.model_copy(
                update={
                    "reason_codes": result.reason_codes,
                    "policy_result": result,
                    "suggested_capital_pct": ZERO,
                }
            )

        if _blocks_new_buy(policy_state, kill_switch) and working.action is Action.BUY:
            reasons.extend(_no_new_buy_reasons(policy_state, kill_switch))
            reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
            working = _as_wait(working) if policy_state is PolicyState.UNKNOWN else _as_no_trade(
                working
            )
            blocked_action = (
                PolicyAction.DEFER if policy_state is PolicyState.UNKNOWN else PolicyAction.REJECT
            )
            result = PolicyResult(
                policy_state=policy_state,
                kill_switch_level=kill_switch,
                action=blocked_action,
                original_suggested_capital_pct=original_pct,
                applied_suggested_capital_pct=ZERO,
                reason_codes=_unique(list(proposal.reason_codes) + reasons),
                force_sell_all=False,
                capital_remaining=remaining_capital,
                risk_remaining=remaining_risk,
            )
            return working.model_copy(
                update={
                    "reason_codes": result.reason_codes,
                    "policy_result": result,
                    "suggested_capital_pct": ZERO,
                }
            )

        if working.action is Action.BUY:
            pct, clamp_reasons, reject_reasons = _constrain_buy(
                pct,
                capital=capital,
                book=book,
                budgets=budgets,
                estimated_risk=working.estimated_risk,
                horizon=working.horizon,
                policy_state=policy_state,
                kill_switch=kill_switch,
            )
            reasons.extend(clamp_reasons)
            if reject_reasons:
                reasons.extend(reject_reasons)
                reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
                working = _as_no_trade(working)
                result = PolicyResult(
                    policy_state=policy_state,
                    kill_switch_level=kill_switch,
                    action=PolicyAction.REJECT,
                    original_suggested_capital_pct=original_pct,
                    applied_suggested_capital_pct=ZERO,
                    reason_codes=_unique(list(proposal.reason_codes) + reasons),
                    force_sell_all=False,
                    capital_remaining=remaining_capital,
                    risk_remaining=remaining_risk,
                )
                return working.model_copy(
                    update={
                        "reason_codes": result.reason_codes,
                        "policy_result": result,
                        "suggested_capital_pct": ZERO,
                    }
                )
            if pct < original_pct:
                action = PolicyAction.CLAMP
                working = working.model_copy(update={"suggested_capital_pct": pct})

        result = PolicyResult(
            policy_state=policy_state,
            kill_switch_level=kill_switch,
            action=action,
            original_suggested_capital_pct=original_pct,
            applied_suggested_capital_pct=working.suggested_capital_pct,
            reason_codes=_unique(list(proposal.reason_codes) + reasons),
            force_sell_all=False,
            capital_remaining=remaining_capital,
            risk_remaining=remaining_risk,
        )
        return working.model_copy(
            update={
                "reason_codes": result.reason_codes,
                "policy_result": result,
            }
        )


def _hard_halt(
    proposal: TradeProposal,
    override: HumanOverride,
    policy_state: PolicyState,
    kill_switch: KillSwitchLevel,
    book: PortfolioContext,
) -> tuple[PolicyAction, PolicyState, list[str]] | None:
    """Returns (policy_action, state, reasons) when the proposal must stop."""

    if not override.ai_enabled:
        return (
            PolicyAction.REJECT,
            PolicyState.AI_DISABLED,
            [
                ReasonCode.HUMAN_AI_DISABLED.value,
                ReasonCode.POLICY_AI_DISABLED.value,
                ReasonCode.POLICY_NO_TRADE_IS_VALID.value,
            ],
        )
    if kill_switch is KillSwitchLevel.LEVEL_4_ALL_TRADING_DISABLED:
        return (
            PolicyAction.REJECT,
            policy_state,
            [
                ReasonCode.POLICY_ALL_TRADING_DISABLED.value,
                ReasonCode.POLICY_NOT_FORCE_SELL_ALL.value,
                ReasonCode.POLICY_NO_TRADE_IS_VALID.value,
            ],
        )
    if (
        kill_switch is KillSwitchLevel.LEVEL_3_AI_DISABLED
        or policy_state is PolicyState.AI_DISABLED
    ):
        return (
            PolicyAction.REJECT,
            PolicyState.AI_DISABLED,
            [
                ReasonCode.POLICY_AI_DISABLED.value,
                ReasonCode.POLICY_NO_TRADE_IS_VALID.value,
            ],
        )
    if override.blocks_symbol(proposal.ticker):
        return (
            PolicyAction.REJECT,
            policy_state,
            [
                ReasonCode.HUMAN_SYMBOL_BLACKLIST.value,
                ReasonCode.POLICY_NO_TRADE_IS_VALID.value,
            ],
        )
    if override.blocks_sector(book.proposal_sector):
        return (
            PolicyAction.REJECT,
            policy_state,
            [
                ReasonCode.HUMAN_SECTOR_BLACKLIST.value,
                ReasonCode.POLICY_NO_TRADE_IS_VALID.value,
            ],
        )
    if (
        proposal.action is Action.BUY
        and proposal.horizon is Horizon.LONG_TERM
        and not override.long_agent_enabled
    ):
        return (
            PolicyAction.REJECT,
            policy_state,
            [
                ReasonCode.HUMAN_LONG_AGENT_DISABLED.value,
                ReasonCode.POLICY_NO_TRADE_IS_VALID.value,
            ],
        )
    if (
        proposal.action is Action.BUY
        and proposal.horizon is Horizon.SHORT_TERM
        and not override.short_agent_enabled
    ):
        return (
            PolicyAction.REJECT,
            policy_state,
            [
                ReasonCode.HUMAN_SHORT_AGENT_DISABLED.value,
                ReasonCode.POLICY_NO_TRADE_IS_VALID.value,
            ],
        )
    return None


def _blocks_new_buy(policy_state: PolicyState, kill_switch: KillSwitchLevel) -> bool:
    if policy_state in {PolicyState.UNKNOWN, PolicyState.NO_NEW_BUY}:
        return True
    return kill_switch is KillSwitchLevel.LEVEL_1_NO_NEW_BUY


def _no_new_buy_reasons(
    policy_state: PolicyState, kill_switch: KillSwitchLevel
) -> list[str]:
    reasons: list[str] = []
    if policy_state is PolicyState.UNKNOWN:
        reasons.append(ReasonCode.POLICY_UNKNOWN_NO_NEW_BUY.value)
    if (
        policy_state is PolicyState.NO_NEW_BUY
        or kill_switch is KillSwitchLevel.LEVEL_1_NO_NEW_BUY
    ):
        reasons.append(ReasonCode.POLICY_NO_NEW_BUY.value)
    if not reasons:
        reasons.append(ReasonCode.POLICY_NO_NEW_BUY.value)
    return reasons


def _constrain_buy(
    desired_pct: Decimal,
    *,
    capital: CapitalContext,
    book: PortfolioContext,
    budgets: RiskBudgets,
    estimated_risk: Decimal,
    horizon: Horizon,
    policy_state: PolicyState,
    kill_switch: KillSwitchLevel,
) -> tuple[Decimal, list[str], list[str]]:
    """Returns (pct, clamp_reasons, reject_reasons)."""

    clamp_reasons: list[str] = []
    reject_reasons: list[str] = []
    pct = min(max(desired_pct, ZERO), HUNDRED)

    if not capital.was_provided or capital.ai_capital_limit <= 0:
        reject_reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
        return ZERO, clamp_reasons, reject_reasons

    remaining_ai = _remaining_ai_capital(capital, book)
    if remaining_ai <= 0:
        reject_reasons.append(ReasonCode.AI_CAPITAL_LIMIT_EXCEEDED.value)
        reject_reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
        return ZERO, clamp_reasons, reject_reasons

    max_pct = _amount_to_pct(remaining_ai, capital.ai_capital_limit)
    if pct > max_pct:
        pct = max_pct
        clamp_reasons.append(ReasonCode.AI_CAPITAL_CLAMPED.value)
        if remaining_ai < capital.ai_capital_limit:
            clamp_reasons.append(ReasonCode.AI_CAPITAL_LIMIT_EXCEEDED.value)

    remaining_horizon = _remaining_horizon_budget(capital, book, horizon)
    horizon_pct = _amount_to_pct(remaining_horizon, capital.ai_capital_limit)
    if pct > horizon_pct:
        pct = horizon_pct
        clamp_reasons.append(ReasonCode.HORIZON_BUDGET_CLAMPED.value)

    if budgets.daily_loss.remaining <= 0:
        reject_reasons.append(ReasonCode.DAILY_LOSS_BUDGET_EXHAUSTED.value)
        return ZERO, clamp_reasons, reject_reasons
    if budgets.ai_drawdown.remaining <= 0:
        reject_reasons.append(ReasonCode.AI_DRAWDOWN_BUDGET_EXHAUSTED.value)
        return ZERO, clamp_reasons, reject_reasons

    risk_pct = _risk_capped_pct(capital, budgets, estimated_risk)
    if pct > risk_pct:
        pct = risk_pct
        clamp_reasons.append(ReasonCode.RISK_BUDGET_CLAMPED.value)
        clamp_reasons.append(ReasonCode.PER_POSITION_RISK_CLAMPED.value)

    bucket_caps = (
        (budgets.sector, ReasonCode.SECTOR_RISK_CLAMPED),
        (budgets.theme, ReasonCode.THEME_RISK_CLAMPED),
        (budgets.country, ReasonCode.COUNTRY_RISK_CLAMPED),
        (budgets.currency, ReasonCode.CURRENCY_RISK_CLAMPED),
        (budgets.tail, ReasonCode.TAIL_RISK_CLAMPED),
        (budgets.liquidity, ReasonCode.LIQUIDITY_RISK_CLAMPED),
    )
    for bucket, code in bucket_caps:
        if bucket.remaining <= 0:
            reject_reasons.append(code.value)
            return ZERO, clamp_reasons, reject_reasons

    if (
        policy_state is PolicyState.REDUCED_EXPOSURE
        or kill_switch is KillSwitchLevel.LEVEL_2_REDUCE_EXPOSURE
    ):
        scaled = (desired_pct * REDUCED_EXPOSURE_SCALE).quantize(Decimal("0.01"))
        if pct > scaled:
            pct = scaled
        clamp_reasons.append(ReasonCode.POLICY_REDUCED_EXPOSURE.value)

    if book.pairwise_correlation_max >= CORRELATION_REDUCTION_THRESHOLD:
        scaled = (desired_pct * (Decimal("1") - book.pairwise_correlation_max)).quantize(
            Decimal("0.01")
        )
        if pct > scaled:
            pct = scaled
        clamp_reasons.append(ReasonCode.HIGH_CORRELATION_EXPOSURE_REDUCED.value)

    if book.stress_correlation >= STRESS_CORRELATION_THRESHOLD:
        scaled = (desired_pct * REDUCED_EXPOSURE_SCALE).quantize(Decimal("0.01"))
        if pct > scaled:
            pct = scaled
        clamp_reasons.append(ReasonCode.STRESS_CORRELATION_REDUCED.value)

    if pct <= 0:
        reject_reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
        if ReasonCode.AI_CAPITAL_LIMIT_EXCEEDED.value not in reject_reasons + clamp_reasons:
            reject_reasons.append(ReasonCode.AI_CAPITAL_LIMIT_EXCEEDED.value)
        return ZERO, clamp_reasons, reject_reasons

    return pct, _unique(clamp_reasons), _unique(reject_reasons)


def _remaining_ai_capital(capital: CapitalContext, book: PortfolioContext) -> Decimal:
    leftover = capital.ai_capital_limit - book.used_ai_capital
    return leftover if leftover > 0 else ZERO


def _remaining_horizon_budget(
    capital: CapitalContext, book: PortfolioContext, horizon: Horizon
) -> Decimal:
    if horizon is Horizon.LONG_TERM:
        leftover = capital.long_term_budget - book.used_long_budget
    elif horizon is Horizon.SHORT_TERM:
        leftover = capital.short_term_budget - book.used_short_budget
    else:
        leftover = capital.ai_capital_limit
    return leftover if leftover > 0 else ZERO


def _amount_to_pct(amount: Decimal, limit: Decimal) -> Decimal:
    if limit <= 0:
        return ZERO
    pct = (amount / limit) * HUNDRED
    if pct < 0:
        return ZERO
    return min(pct, HUNDRED)


def _risk_capped_pct(
    capital: CapitalContext, budgets: RiskBudgets, estimated_risk: Decimal
) -> Decimal:
    """Map remaining loss budget onto a percent of AI capital.

    Capital limit and risk budget stay separate: a large unused capital
    sleeve cannot override an exhausted loss budget.
    """

    remaining_loss = min(
        budgets.per_position.remaining,
        budgets.daily_loss.remaining,
        budgets.ai_drawdown.remaining,
        capital.risk_budget,
    )
    if remaining_loss <= 0:
        return ZERO
    if estimated_risk <= 0:
        return HUNDRED
    max_notional = remaining_loss / estimated_risk
    return _amount_to_pct(max_notional, capital.ai_capital_limit)


def _as_no_trade(proposal: TradeProposal) -> TradeProposal:
    return proposal.model_copy(
        update={
            "action": Action.NO_TRADE,
            "horizon": Horizon.NONE,
            "suggested_capital_pct": ZERO,
            "expected_holding_period": 0,
            "expected_return": ZERO,
            "estimated_risk": ZERO,
        }
    )


def _as_wait(proposal: TradeProposal) -> TradeProposal:
    return proposal.model_copy(
        update={
            "action": Action.TACTICAL_WAIT,
            "horizon": Horizon.NONE,
            "suggested_capital_pct": ZERO,
            "expected_holding_period": 0,
            "expected_return": ZERO,
            "estimated_risk": ZERO,
        }
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
