from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.enums import DecisionType, Horizon
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.ports.llm import LlmRequest, LlmResponse


class FixtureLlmProvider:
    """Returns canned judgment fragments. No remote model is called."""

    def __init__(self, desired: DecisionType, raw_confidence: float = 0.7) -> None:
        self.desired = desired
        self.raw_confidence = raw_confidence
        self.suggested_capital_pct = Decimal("5")
        self.calls: list[LlmRequest] = []

    def complete(self, request: LlmRequest) -> LlmResponse:
        self.calls.append(request)
        horizon = Horizon.LONG_TERM
        if self.desired is DecisionType.SHORT_TERM_BUY:
            horizon = Horizon.SHORT_TERM
        elif self.desired in {
            DecisionType.NO_TRADE,
            DecisionType.TACTICAL_WAIT,
            DecisionType.HOLD,
            DecisionType.SELL,
            DecisionType.EXIT_REVIEW,
        }:
            horizon = Horizon.NONE
        thesis = InvestmentThesis(
            headline=f"Fixture thesis for {request.ticker}",
            summary="Fixture LLM adapter. Not a live model.",
            bull_case="Opportunity exists only if gates allow it.",
            bear_case="Capital preservation outranks return seeking.",
            time_horizon=horizon,
            catalysts=["fixture"],
            risks=["unknown regime", "missing capital"],
            invalidation_summary="Invalidate if data quality collapses.",
        )
        return LlmResponse(
            model_name="fixture-llm",
            raw_text="fixture",
            content={
                "desiredDecision": self.desired.value,
                "rawConfidence": self.raw_confidence,
                "suggestedCapitalPct": str(self.suggested_capital_pct),
                "thesis": thesis.model_dump(mode="json"),
                "invalidationConditions": [
                    InvalidationCondition(
                        code="DATA_QUALITY_BREAK",
                        description="Snapshot completeness falls below policy threshold.",
                    ).model_dump(mode="json")
                ],
            },
        )
