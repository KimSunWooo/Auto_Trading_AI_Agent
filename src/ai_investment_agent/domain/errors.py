from __future__ import annotations


class DomainError(Exception):
    """Base class for recoverable domain rule violations."""


class InvalidDecisionError(DomainError):
    pass


class SerializationError(DomainError):
    pass


class DecisionNotFoundError(DomainError):
    def __init__(self, decision_id: str) -> None:
        super().__init__(f"No journal snapshot for decisionId={decision_id}")
        self.decision_id = decision_id


class OnlineLearningForbiddenError(DomainError):
    """Losses must not rewrite the live model between judgments."""
