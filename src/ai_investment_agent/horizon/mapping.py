from __future__ import annotations

from ai_investment_agent.domain.enums import Horizon

DEFAULT_LONG_TERM_DAYS = 252
DEFAULT_SHORT_TERM_DAYS = 20


def holding_period_days(horizon: Horizon) -> int | None:
    if horizon is Horizon.LONG_TERM:
        return DEFAULT_LONG_TERM_DAYS
    if horizon is Horizon.SHORT_TERM:
        return DEFAULT_SHORT_TERM_DAYS
    return None
