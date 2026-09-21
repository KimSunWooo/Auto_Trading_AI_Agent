"""Offline model promotion. Online self-learning is forbidden."""

from __future__ import annotations

from ai_investment_agent.domain.enums import ModelLifecycleStage
from ai_investment_agent.domain.errors import OnlineLearningForbiddenError
from ai_investment_agent.domain.evaluation import ModelLifecyclePlan

PROMOTION_PATH: tuple[ModelLifecycleStage, ...] = ModelLifecyclePlan().stages


class ModelPromotionService:
    """Decision Logs → Offline Evaluation → Candidate → Backtest → Shadow → Approval → New Version.

    There is no path from a live loss to an immediate strategy rewrite.
    """

    def __init__(self, plan: ModelLifecyclePlan | None = None) -> None:
        self._plan = plan or ModelLifecyclePlan()

    @property
    def plan(self) -> ModelLifecyclePlan:
        return self._plan

    def current(self) -> ModelLifecycleStage:
        return self._plan.current

    def can_advance_to(self, target: ModelLifecycleStage) -> bool:
        order = list(PROMOTION_PATH)
        try:
            here = order.index(self._plan.current)
            there = order.index(target)
        except ValueError:
            return False
        return there == here + 1

    def advance(self, target: ModelLifecycleStage) -> ModelLifecyclePlan:
        if not self.can_advance_to(target):
            raise ValueError(
                f"Cannot jump from {self._plan.current.value} to {target.value}"
            )
        self._plan = self._plan.model_copy(update={"current": target})
        return self._plan

    def apply_online_update(self, *_args: object, **_kwargs: object) -> None:
        raise OnlineLearningForbiddenError(
            "Losses must not auto-rewrite the live model. "
            "Use Decision Logs → Offline Evaluation → Candidate Model → "
            "Backtest → Shadow → Approval → New Version."
        )
