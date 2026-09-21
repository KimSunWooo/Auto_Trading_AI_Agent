from __future__ import annotations

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import Horizon


class InvalidationCondition(DomainModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)


class InvestmentThesis(DomainModel):
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    bull_case: str
    bear_case: str
    time_horizon: Horizon = Horizon.NONE
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    invalidation_summary: str = ""
