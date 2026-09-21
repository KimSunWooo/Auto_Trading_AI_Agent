from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel


class LlmRequest(DomainModel):
    task: str
    ticker: str
    payload: dict[str, Any] = Field(default_factory=dict)


class LlmResponse(DomainModel):
    content: dict[str, Any] = Field(default_factory=dict)
    model_name: str = "fixture-llm"
    raw_text: str = ""


class LlmProvider(Protocol):
    """Vendor-agnostic language model port.

    Adapters may wrap an SDK later. Domain code must not import those SDKs.
    """

    def complete(self, request: LlmRequest) -> LlmResponse:
        ...
