from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from ai_investment_agent.domain.agent_views import AgentAssessment
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.confidence import ConfidenceAssessment
from ai_investment_agent.domain.context import MarketContext
from ai_investment_agent.domain.enums import Action, HorizonChoice, JournalStage
from ai_investment_agent.domain.evaluation import CounterfactualOutcome, VersionPin
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis


class DecisionJournalEntry(DomainModel):
    journal_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    stage: JournalStage
    message: str
    reason_codes: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime


class DecisionRecord(DomainModel):
    """Canonical journal document for one judgment. BUY is not required.

    SELL, HOLD, TACTICAL_WAIT, NO_TRADE, and EXIT_REVIEW are first-class.
    """

    decision_id: str = Field(min_length=1)
    timestamp: datetime
    ticker: str = Field(min_length=1)
    market_snapshot: MarketSnapshot
    event_snapshot: list[MarketEvent] = Field(default_factory=list)
    feature_snapshot: MarketContext | None = None
    market_regime: MarketRegime
    long_analysis: AgentAssessment | None = None
    short_analysis: AgentAssessment | None = None
    selected_horizon: HorizonChoice | None = None
    action: Action
    raw_confidence: float = Field(ge=0, le=1)
    calibrated_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_is_probability: Literal[False] = False
    expected_return: Decimal
    estimated_risk: Decimal = Field(ge=0)
    suggested_capital_pct: Decimal = Field(ge=0, le=100)
    reason_codes: list[str] = Field(default_factory=list)
    thesis: InvestmentThesis
    invalidation_conditions: list[InvalidationCondition] = Field(default_factory=list)
    model_version: str
    prompt_version: str
    feature_version: str
    policy_version: str
    counterfactual: CounterfactualOutcome = Field(default_factory=CounterfactualOutcome)

    @property
    def versions(self) -> VersionPin:
        return VersionPin(
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            feature_version=self.feature_version,
            policy_version=self.policy_version,
        )

    @property
    def confidence(self) -> ConfidenceAssessment:
        return ConfidenceAssessment(
            raw_confidence=self.raw_confidence,
            calibrated_confidence=self.calibrated_confidence,
            treated_as_probability=False,
            calibration_applied=self.calibrated_confidence is not None,
        )
