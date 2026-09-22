"""LIVE_OBSERVATION capital / portfolio context. Not a real brokerage account."""

from __future__ import annotations

import os
from decimal import Decimal

from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.policy import PortfolioContext, RiskBudgets


def _decimal(name: str, default: str) -> Decimal:
    return Decimal(os.environ.get(name, default))


def observation_capital_from_env() -> CapitalContext:
    """Reference observation capital from env. source=observation_config, not a live account."""
    return CapitalContext(
        total_capital=_decimal("OBSERVATION_TOTAL_CAPITAL", "100000000"),
        ai_capital_limit=_decimal("OBSERVATION_AI_CAPITAL_LIMIT", "10000000"),
        ai_capital_ratio=Decimal(os.environ.get("OBSERVATION_AI_CAPITAL_RATIO", "0.10")),
        long_term_budget=_decimal("OBSERVATION_LONG_BUDGET", "7000000"),
        short_term_budget=_decimal("OBSERVATION_SHORT_BUDGET", "3000000"),
        reserve_cash=_decimal("OBSERVATION_RESERVE_CASH", "20000000"),
        risk_budget=_decimal("OBSERVATION_RISK_BUDGET", "5000000"),
        source="observation_config",
    )


def observation_portfolio_from_env() -> PortfolioContext:
    """Independent observation book. Never loaded from Auto-Trading-system."""
    return PortfolioContext(
        source="observation_config",
        used_ai_capital=_decimal("OBSERVATION_USED_AI_CAPITAL", "0"),
        used_long_budget=_decimal("OBSERVATION_USED_LONG_BUDGET", "0"),
        used_short_budget=_decimal("OBSERVATION_USED_SHORT_BUDGET", "0"),
        cash=_decimal("OBSERVATION_CASH", "10000000"),
    )


def observation_risk_budgets() -> RiskBudgets:
    """Open observation risk budgets. Not ATS RiskManager state."""
    return RiskBudgets.fixture_open()
