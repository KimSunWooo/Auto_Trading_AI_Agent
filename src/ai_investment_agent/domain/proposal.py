from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import Action, DecisionType, Horizon
from ai_investment_agent.domain.errors import InvalidDecisionError
from ai_investment_agent.domain.market import MarketRegime
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.domain.versions import FEATURE_VERSION, MODEL_VERSION, POLICY_VERSION


class TradeProposal(DomainModel):
    """Judgment artifact for a later consumer. This is not an order.

    suggestedCapitalPct is a recommended fraction of AI-allocatable capital
    (0-100). It is not an order size, not a cash amount, and not a
    instruction to any broker.
    """

    decision_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    horizon: Horizon
    action: Action
    raw_confidence: float = Field(ge=0, le=1)
    calibrated_confidence: float = Field(ge=0, le=1)
    expected_return: Decimal
    estimated_risk: Decimal = Field(ge=0)
    suggested_capital_pct: Decimal = Field(ge=0, le=100)
    expected_holding_period: int | None = Field(
        default=None,
        ge=0,
        description="Expected holding period in days. None when horizon is NONE.",
    )
    thesis: InvestmentThesis
    invalidation_conditions: list[InvalidationCondition] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    market_regime: MarketRegime
    model_version: str = MODEL_VERSION
    feature_version: str = FEATURE_VERSION
    policy_version: str = POLICY_VERSION
    generated_at: datetime

    @property
    def decision(self) -> DecisionType:
        return decision_type_for(self.action, self.horizon)

    @model_validator(mode="after")
    def check_action_horizon_and_capital(self) -> TradeProposal:
        try:
            decision_type_for(self.action, self.horizon)
        except InvalidDecisionError as exc:
            raise ValueError(str(exc)) from exc

        if self.horizon is Horizon.NONE and self.expected_holding_period not in (None, 0):
            raise ValueError("expectedHoldingPeriod must be empty or 0 when horizon is NONE")

        if self.action in {Action.NO_TRADE, Action.TACTICAL_WAIT} and self.suggested_capital_pct != 0:
            raise ValueError("NO_TRADE and TACTICAL_WAIT must use suggestedCapitalPct=0")
        return self


def decision_type_for(action: Action, horizon: Horizon) -> DecisionType:
    if action is Action.BUY:
        if horizon is Horizon.LONG_TERM:
            return DecisionType.LONG_TERM_BUY
        if horizon is Horizon.SHORT_TERM:
            return DecisionType.SHORT_TERM_BUY
        raise InvalidDecisionError("BUY requires LONG_TERM or SHORT_TERM horizon")
    if action is Action.SELL:
        return DecisionType.SELL
    if action is Action.HOLD:
        return DecisionType.HOLD
    if action is Action.NO_TRADE:
        if horizon is not Horizon.NONE:
            raise InvalidDecisionError("NO_TRADE requires horizon NONE")
        return DecisionType.NO_TRADE
    if action is Action.TACTICAL_WAIT:
        if horizon is not Horizon.NONE:
            raise InvalidDecisionError("TACTICAL_WAIT requires horizon NONE")
        return DecisionType.TACTICAL_WAIT
    if action is Action.EXIT_REVIEW:
        return DecisionType.EXIT_REVIEW
    raise InvalidDecisionError(f"Unsupported action/horizon pair: {action}/{horizon}")


def action_horizon_for(decision: DecisionType) -> tuple[Action, Horizon]:
    mapping: dict[DecisionType, tuple[Action, Horizon]] = {
        DecisionType.LONG_TERM_BUY: (Action.BUY, Horizon.LONG_TERM),
        DecisionType.SHORT_TERM_BUY: (Action.BUY, Horizon.SHORT_TERM),
        DecisionType.HOLD: (Action.HOLD, Horizon.NONE),
        DecisionType.SELL: (Action.SELL, Horizon.NONE),
        DecisionType.NO_TRADE: (Action.NO_TRADE, Horizon.NONE),
        DecisionType.TACTICAL_WAIT: (Action.TACTICAL_WAIT, Horizon.NONE),
        DecisionType.EXIT_REVIEW: (Action.EXIT_REVIEW, Horizon.NONE),
    }
    return mapping[decision]
