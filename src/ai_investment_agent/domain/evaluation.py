"""Evaluation, counterfactual outcomes, model health, and promotion path.

Execution Quality is reserved for a later broker-connected phase and is
not implemented here. Online self-learning is forbidden.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import (
    EvaluationStatus,
    ModelHealthStatus,
    ModelLifecycleStage,
    QualityAxis,
)


class CounterfactualOutcome(DomainModel):
    """Ex-post path metrics. No live order is required to fill these later."""

    return_1h: Decimal | None = None
    return_1d: Decimal | None = None
    return_5d: Decimal | None = None
    return_20d: Decimal | None = None
    mfe: Decimal | None = None
    mae: Decimal | None = None
    measured_at: datetime | None = None
    source: Literal["unmeasured", "fixture_price_path"] = "unmeasured"

    @property
    def is_measured(self) -> bool:
        if self.source == "unmeasured":
            return False
        return any(
            value is not None
            for value in (
                self.return_1h,
                self.return_1d,
                self.return_5d,
                self.return_20d,
                self.mfe,
                self.mae,
            )
        )


class VersionPin(DomainModel):
    model_version: str
    prompt_version: str
    feature_version: str
    policy_version: str


class QualityScore(DomainModel):
    axis: QualityAxis
    status: EvaluationStatus = EvaluationStatus.PENDING
    score: Decimal | None = None
    sample_size: int = Field(default=0, ge=0)


class OfflineEvaluationReport(DomainModel):
    """Four judgment axes only. Execution Quality is intentionally absent."""

    alpha: QualityScore
    horizon_selection: QualityScore
    risk_assessment: QualityScore
    capital_allocation: QualityScore
    evaluated_at: datetime | None = None

    @property
    def axes(self) -> tuple[QualityScore, ...]:
        return (
            self.alpha,
            self.horizon_selection,
            self.risk_assessment,
            self.capital_allocation,
        )


class ModelHealthMetrics(DomainModel):
    status: ModelHealthStatus = ModelHealthStatus.UNKNOWN
    win_rate: float | None = Field(default=None, ge=0, le=1)
    expected_value: Decimal | None = None
    drawdown: Decimal | None = None
    sharpe: float | None = None
    calibration_error: float | None = Field(default=None, ge=0)
    decision_distribution: dict[str, int] = Field(default_factory=dict)
    proposal_frequency: float | None = Field(default=None, ge=0)
    average_confidence: float | None = Field(default=None, ge=0, le=1)
    average_confidence_is_probability: Literal[False] = False
    sample_size: int = Field(default=0, ge=0)
    outcome_sample_size: int = Field(default=0, ge=0)

    @classmethod
    def unknown(cls) -> ModelHealthMetrics:
        return cls(status=ModelHealthStatus.UNKNOWN)

    @property
    def treated_as_healthy(self) -> bool:
        return self.status is ModelHealthStatus.HEALTHY


class ModelLifecyclePlan(DomainModel):
    """Required promotion path. There is no online-update stage."""

    stages: tuple[ModelLifecycleStage, ...] = (
        ModelLifecycleStage.DECISION_LOGS,
        ModelLifecycleStage.OFFLINE_EVALUATION,
        ModelLifecycleStage.CANDIDATE_MODEL,
        ModelLifecycleStage.BACKTEST,
        ModelLifecycleStage.SHADOW,
        ModelLifecycleStage.APPROVED,
        ModelLifecycleStage.NEW_VERSION,
    )
    current: ModelLifecycleStage = ModelLifecycleStage.DECISION_LOGS
    online_self_learning: Literal[False] = False
