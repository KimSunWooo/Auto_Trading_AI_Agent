"""Fixture portfolio / human-override builders. Not a live ATS book."""

from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.policy import (
    HumanOverride,
    PortfolioContext,
    RiskBudgets,
)


def fixture_portfolio(
    *,
    used_ai_capital: Decimal = Decimal("0"),
    used_long_budget: Decimal = Decimal("0"),
    used_short_budget: Decimal = Decimal("0"),
    pairwise_correlation_max: Decimal = Decimal("0"),
    stress_correlation: Decimal = Decimal("0"),
    proposal_sector: str | None = None,
) -> PortfolioContext:
    return PortfolioContext(
        source="fixture",
        used_ai_capital=used_ai_capital,
        used_long_budget=used_long_budget,
        used_short_budget=used_short_budget,
        pairwise_correlation_max=pairwise_correlation_max,
        stress_correlation=stress_correlation,
        proposal_sector=proposal_sector,
    )


def fixture_human_override(
    *,
    ai_enabled: bool = True,
    long_agent_enabled: bool = True,
    short_agent_enabled: bool = True,
    symbol_blacklist: tuple[str, ...] = (),
    sector_blacklist: tuple[str, ...] = (),
) -> HumanOverride:
    return HumanOverride(
        ai_enabled=ai_enabled,
        long_agent_enabled=long_agent_enabled,
        short_agent_enabled=short_agent_enabled,
        symbol_blacklist=symbol_blacklist,
        sector_blacklist=sector_blacklist,
    )


def fixture_risk_budgets() -> RiskBudgets:
    return RiskBudgets.fixture_open()
