"""Structured LLM output schema. Free text is never used as a decision."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, ValidationError

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import DecisionType, Horizon
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis


class StructuredLlmJudgment(DomainModel):
    """Validated LLM payload for thesis / classification assistance only.

    Does not authorize orders, quantity, capital overrides, or kill-switch changes.
    """

    desired_decision: DecisionType = Field(alias="desiredDecision")
    raw_confidence: float = Field(alias="rawConfidence", ge=0.0, le=1.0)
    suggested_capital_pct: str = Field(alias="suggestedCapitalPct", default="0")
    thesis: InvestmentThesis
    invalidation_conditions: list[InvalidationCondition] = Field(
        default_factory=list,
        alias="invalidationConditions",
    )
    summary: str | None = None
    event_classification: str | None = Field(default=None, alias="eventClassification")
    llm_status: Literal["OK"] = Field(default="OK", alias="llmStatus")

    model_config = {"populate_by_name": True}


def parse_structured_judgment(payload: dict[str, Any]) -> StructuredLlmJudgment:
    try:
        return StructuredLlmJudgment.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"LLM structured output invalid: {exc}") from exc


def fail_closed_content(*, reason: str) -> dict[str, Any]:
    """Explicit failure payload. Never a fabricated BUY."""
    thesis = InvestmentThesis(
        headline="LLM unavailable",
        summary=f"LLM_FAILED: {reason}. Fail-closed — no fabricated buy.",
        bull_case="Not evaluated.",
        bear_case="Model output unavailable; capital preservation preferred.",
        time_horizon=Horizon.NONE,
        risks=["LLM_FAILED"],
        invalidation_summary="Invalidate any prior LLM-assisted thesis.",
    )
    return {
        "desiredDecision": DecisionType.NO_TRADE.value,
        "rawConfidence": 0.0,
        "suggestedCapitalPct": "0",
        "thesis": thesis.model_dump(mode="json"),
        "invalidationConditions": [
            {
                "code": "LLM_FAILED",
                "description": reason,
            }
        ],
        "llmStatus": "LLM_FAILED",
    }
