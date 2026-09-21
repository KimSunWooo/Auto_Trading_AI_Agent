from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.agent_views import AgentAssessment, HorizonDecision
from ai_investment_agent.domain.enums import (
    HorizonChoice,
    MarketRegimeType,
    ReasonCode,
    Stance,
)
from ai_investment_agent.domain.market import MarketRegime
from ai_investment_agent.policy.utility import UtilityConfig


class HorizonSelector:
    """Chooses LONG_TERM, SHORT_TERM, TACTICAL_WAIT, or NO_TRADE.

    Long and short assessments are never averaged.
    """

    def __init__(self, config: UtilityConfig | None = None) -> None:
        self.config = config or UtilityConfig()

    def select(
        self,
        long_view: AgentAssessment,
        short_view: AgentAssessment,
        regime: MarketRegime,
    ) -> HorizonDecision:
        reasons: list[str] = []
        if regime.regime is MarketRegimeType.UNKNOWN:
            reasons.append(ReasonCode.UNKNOWN_MARKET_REGIME.value)
            reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
            return _decision(HorizonChoice.NO_TRADE, long_view, short_view, reasons)

        long_ok = _viable(long_view, self.config.min_net_edge)
        short_ok = _viable(short_view, self.config.min_net_edge)

        if long_view.stance is Stance.BULLISH:
            reasons.append(ReasonCode.LONG_THESIS_VALID.value)
        if short_view.stance is Stance.BULLISH:
            reasons.append(ReasonCode.SHORT_THESIS_VALID.value)
        if short_view.stance is Stance.BEARISH:
            reasons.append(ReasonCode.SHORT_BEARISH.value)

        if long_view.stance is Stance.BULLISH and short_view.stance is Stance.BEARISH:
            reasons.append(ReasonCode.LONG_SHORT_CONFLICT.value)
            return _decision(HorizonChoice.TACTICAL_WAIT, long_view, short_view, reasons)

        if not long_ok and not short_ok:
            if _weak_pair(long_view, short_view):
                reasons.append(ReasonCode.BOTH_AGENTS_WEAK.value)
            reasons.append(ReasonCode.LOW_NET_EDGE.value)
            reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)
            return _decision(HorizonChoice.NO_TRADE, long_view, short_view, reasons)

        if long_ok and short_ok:
            assert long_view.net_edge is not None and short_view.net_edge is not None
            gap = abs(long_view.net_edge - short_view.net_edge)
            if gap < self.config.dominance_margin:
                reasons.append(ReasonCode.HORIZON_UNRESOLVED.value)
                return _decision(HorizonChoice.TACTICAL_WAIT, long_view, short_view, reasons)
            choice = (
                HorizonChoice.LONG_TERM
                if long_view.net_edge > short_view.net_edge
                else HorizonChoice.SHORT_TERM
            )
            return _decision(choice, long_view, short_view, reasons)

        if long_ok:
            return _decision(HorizonChoice.LONG_TERM, long_view, short_view, reasons)
        return _decision(HorizonChoice.SHORT_TERM, long_view, short_view, reasons)


def _viable(view: AgentAssessment, min_edge: Decimal) -> bool:
    if view.stance is not Stance.BULLISH:
        return False
    if view.net_edge is None:
        return False
    return view.net_edge >= min_edge


def _weak_pair(long_view: AgentAssessment, short_view: AgentAssessment) -> bool:
    weak = {Stance.WEAK, Stance.NEUTRAL}
    return long_view.stance in weak and short_view.stance in weak


def _decision(
    choice: HorizonChoice,
    long_view: AgentAssessment,
    short_view: AgentAssessment,
    reasons: list[str],
) -> HorizonDecision:
    return HorizonDecision(
        choice=choice,
        long_stance=long_view.stance,
        short_stance=short_view.stance,
        long_net_edge=long_view.net_edge,
        short_net_edge=short_view.net_edge,
        reason_codes=_unique(reasons),
    )


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen
