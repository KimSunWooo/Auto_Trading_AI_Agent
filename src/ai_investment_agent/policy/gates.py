from __future__ import annotations

from dataclasses import dataclass, field

from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import DecisionType, MarketRegimeType, ReasonCode
from ai_investment_agent.domain.market import MarketRegime, MarketSnapshot


@dataclass(frozen=True)
class GateResult:
    decision: DecisionType
    reason_codes: list[str] = field(default_factory=list)
    blocked: bool = False


def apply_hard_gates(
    desired: DecisionType,
    regime: MarketRegime,
    capital: CapitalContext,
    snapshot: MarketSnapshot,
) -> GateResult:
    """Capital preservation gates. NO_TRADE is a first-class success outcome."""

    reasons: list[str] = []

    if regime.regime is MarketRegimeType.UNKNOWN:
        reasons.append(ReasonCode.UNKNOWN_MARKET_REGIME.value)
        reasons.append(ReasonCode.CAPITAL_PRESERVATION_PRIORITY.value)
        if snapshot.data_completeness < 0.3 or snapshot.last_price is None:
            reasons.append(ReasonCode.LOW_DATA_COMPLETENESS.value)
        reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
        return GateResult(DecisionType.NO_TRADE, reasons, blocked=True)

    if snapshot.data_completeness < 0.3 or snapshot.last_price is None:
        reasons.append(ReasonCode.LOW_DATA_COMPLETENESS.value)
        reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
        return GateResult(DecisionType.NO_TRADE, reasons, blocked=True)

    if regime.regime is MarketRegimeType.CRISIS and desired in {
        DecisionType.LONG_TERM_BUY,
        DecisionType.SHORT_TERM_BUY,
    }:
        reasons.append(ReasonCode.CATASTROPHIC_LOSS_PREVENTION.value)
        return GateResult(DecisionType.TACTICAL_WAIT, reasons, blocked=True)

    if not capital.was_provided and desired in {
        DecisionType.LONG_TERM_BUY,
        DecisionType.SHORT_TERM_BUY,
    }:
        reasons.append(ReasonCode.CAPITAL_CONTEXT_MISSING.value)
        reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
        reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
        return GateResult(DecisionType.NO_TRADE, reasons, blocked=True)

    if capital.deployable_capital <= 0 and desired in {
        DecisionType.LONG_TERM_BUY,
        DecisionType.SHORT_TERM_BUY,
    }:
        reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
        reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
        return GateResult(DecisionType.NO_TRADE, reasons, blocked=True)

    return GateResult(desired, reasons, blocked=False)
