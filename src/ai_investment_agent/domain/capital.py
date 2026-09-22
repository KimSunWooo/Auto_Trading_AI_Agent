from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel

CapitalSource = Literal["provided", "missing_conservative_default", "observation_config"]


class CapitalContext(DomainModel):
    """AI-allocatable capital view. This is not an account controller.

    Missing context is never treated as unlimited buying power.
    """

    total_capital: Decimal = Field(ge=0)
    ai_capital_limit: Decimal = Field(ge=0)
    ai_capital_ratio: Decimal = Field(ge=0, le=1)
    long_term_budget: Decimal = Field(ge=0)
    short_term_budget: Decimal = Field(ge=0)
    reserve_cash: Decimal = Field(ge=0)
    risk_budget: Decimal = Field(ge=0)
    source: CapitalSource = "provided"

    @model_validator(mode="after")
    def check_internal_limits(self) -> CapitalContext:
        if self.ai_capital_limit > self.total_capital:
            raise ValueError("aiCapitalLimit cannot exceed totalCapital")
        if self.long_term_budget + self.short_term_budget > self.ai_capital_limit:
            raise ValueError("horizon budgets cannot exceed aiCapitalLimit")
        if self.risk_budget > self.ai_capital_limit:
            raise ValueError("riskBudget cannot exceed aiCapitalLimit")
        if self.reserve_cash > self.total_capital:
            raise ValueError("reserveCash cannot exceed totalCapital")
        return self

    @classmethod
    def missing_conservative(cls) -> CapitalContext:
        """Safe default when the caller omitted capital.

        All deployable amounts are zero. This is explicit scarcity,
        not a missing-value that could be read as unconstrained.
        """

        return cls(
            total_capital=Decimal("0"),
            ai_capital_limit=Decimal("0"),
            ai_capital_ratio=Decimal("0"),
            long_term_budget=Decimal("0"),
            short_term_budget=Decimal("0"),
            reserve_cash=Decimal("0"),
            risk_budget=Decimal("0"),
            source="missing_conservative_default",
        )

    @property
    def was_provided(self) -> bool:
        return self.source == "provided"

    @property
    def deployable_capital(self) -> Decimal:
        return min(self.ai_capital_limit, self.risk_budget)
