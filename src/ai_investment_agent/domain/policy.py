"""AI-side capital / policy / safety models.

This is not a broker RiskManager. Nothing here places, cancels, or
stops live orders. FORCE_SELL_ALL is intentionally absent: kill switch
LEVEL 4 is ALL_TRADING_DISABLED, which is a different meaning.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import KillSwitchLevel, PolicyAction, PolicyState


class HumanOverride(DomainModel):
    """External control plane. The AI agent has no mutator for this object.

    Constructed only by the caller. Frozen so in-process code cannot
    assign fields after construction.
    """

    model_config = ConfigDict(frozen=True)

    ai_enabled: bool = True
    long_agent_enabled: bool = True
    short_agent_enabled: bool = True
    symbol_blacklist: tuple[str, ...] = ()
    sector_blacklist: tuple[str, ...] = ()

    @field_validator("symbol_blacklist", "sector_blacklist", mode="before")
    @classmethod
    def _tupleize(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        return tuple(str(item) for item in value)  # type: ignore[union-attr]

    def blocks_symbol(self, ticker: str) -> bool:
        needle = ticker.strip().upper()
        return any(item.strip().upper() == needle for item in self.symbol_blacklist)

    def blocks_sector(self, sector: str | None) -> bool:
        if sector is None or sector.strip() == "":
            return False
        needle = sector.strip().upper()
        return any(item.strip().upper() == needle for item in self.sector_blacklist)


class RiskBudgetUsage(DomainModel):
    """Allowed loss remaining in one risk bucket. Not deployable capital."""

    limit: Decimal = Field(ge=0)
    used: Decimal = Field(default=Decimal("0"), ge=0)

    @property
    def remaining(self) -> Decimal:
        leftover = self.limit - self.used
        return leftover if leftover > 0 else Decimal("0")


class RiskBudgets(DomainModel):
    """Risk capacity, kept separate from Capital Limit.

    Capital Limit = maximum funds the AI may deploy.
    Risk Budget = maximum loss the AI may accept.
    """

    ai_drawdown: RiskBudgetUsage
    daily_loss: RiskBudgetUsage
    per_position: RiskBudgetUsage
    sector: RiskBudgetUsage
    theme: RiskBudgetUsage
    country: RiskBudgetUsage
    currency: RiskBudgetUsage
    correlation: RiskBudgetUsage
    stress_correlation: RiskBudgetUsage
    tail: RiskBudgetUsage
    liquidity: RiskBudgetUsage

    @classmethod
    def fixture_open(cls) -> RiskBudgets:
        """Fixture with unused capacity. Not a live risk desk snapshot."""

        def bucket() -> RiskBudgetUsage:
            return RiskBudgetUsage(limit=Decimal("10000000"), used=Decimal("0"))

        return cls(
            ai_drawdown=bucket(),
            daily_loss=bucket(),
            per_position=bucket(),
            sector=bucket(),
            theme=bucket(),
            country=bucket(),
            currency=bucket(),
            correlation=bucket(),
            stress_correlation=bucket(),
            tail=bucket(),
            liquidity=bucket(),
        )


class FixturePositionSlice(DomainModel):
    ticker: str = Field(min_length=1)
    market_value: Decimal = Field(ge=0)
    side: Literal["LONG", "SHORT"] = "LONG"
    sector: str | None = None
    theme: str | None = None
    country: str | None = None
    currency: str | None = None


class PortfolioContext(DomainModel):
    """Policy-layer book view.

    This stage must not read an Auto-Trading-system portfolio.
    Allowed sources: fixture (tests) or observation_config (LIVE_OBSERVATION only).
    ATS portfolio feeds are never accepted.
    """

    source: Literal["fixture", "observation_config"] = "fixture"
    used_ai_capital: Decimal = Field(default=Decimal("0"), ge=0)
    used_long_budget: Decimal = Field(default=Decimal("0"), ge=0)
    used_short_budget: Decimal = Field(default=Decimal("0"), ge=0)
    cash: Decimal = Field(default=Decimal("0"), ge=0)
    positions: list[FixturePositionSlice] = Field(default_factory=list)
    pairwise_correlation_max: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    stress_correlation: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    proposal_sector: str | None = None
    proposal_theme: str | None = None
    proposal_country: str | None = None
    proposal_currency: str | None = None

    @classmethod
    def fixture_empty(cls) -> PortfolioContext:
        return cls()


class PolicyResult(DomainModel):
    """Outcome of the AI-side policy layer, attached to a TradeProposal.

    `force_sell_all` is always False here. ALL_TRADING_DISABLED means
    "do not propose trades", not "liquidate the book".
    """

    policy_state: PolicyState
    kill_switch_level: KillSwitchLevel
    action: PolicyAction
    original_suggested_capital_pct: Decimal = Field(ge=0, le=100)
    applied_suggested_capital_pct: Decimal = Field(ge=0, le=100)
    reason_codes: list[str] = Field(default_factory=list)
    force_sell_all: Literal[False] = False
    capital_remaining: Decimal = Field(default=Decimal("0"), ge=0)
    risk_remaining: Decimal = Field(default=Decimal("0"), ge=0)
