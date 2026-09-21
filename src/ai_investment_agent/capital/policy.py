from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import Action, ReasonCode


class CapitalPolicy:
    """Resolves and caps capital usage. Missing context is zero, never infinity."""

    def resolve(self, provided: CapitalContext | None) -> CapitalContext:
        if provided is None:
            return CapitalContext.missing_conservative()
        return provided

    def cap_suggested_pct(
        self,
        desired_pct: Decimal,
        context: CapitalContext,
        action: Action,
    ) -> tuple[Decimal, list[str]]:
        reasons: list[str] = []
        if action in {Action.NO_TRADE, Action.TACTICAL_WAIT, Action.HOLD, Action.EXIT_REVIEW}:
            return Decimal("0"), reasons

        if not context.was_provided:
            reasons.append(ReasonCode.CAPITAL_CONTEXT_MISSING.value)
            return Decimal("0"), reasons

        if context.deployable_capital <= 0 or context.ai_capital_limit <= 0:
            reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
            return Decimal("0"), reasons

        max_from_risk = (context.risk_budget / context.ai_capital_limit) * Decimal("100")
        capped = min(max(desired_pct, Decimal("0")), max_from_risk, Decimal("100"))
        if capped <= 0:
            reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
            return Decimal("0"), reasons
        return capped, reasons
