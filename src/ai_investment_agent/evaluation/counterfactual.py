"""Attach ex-post path metrics to a stored judgment. No order is created."""

from __future__ import annotations

from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.errors import DecisionNotFoundError
from ai_investment_agent.domain.evaluation import CounterfactualOutcome
from ai_investment_agent.ports.repository import DecisionRepository


class CounterfactualRecorder:
    def __init__(self, repository: DecisionRepository) -> None:
        self._repository = repository

    def record(self, decision_id: str, outcome: CounterfactualOutcome) -> DecisionSnapshot:
        updated = self._repository.attach_counterfactual(decision_id, outcome)
        if updated is None:
            raise DecisionNotFoundError(decision_id)
        return updated
