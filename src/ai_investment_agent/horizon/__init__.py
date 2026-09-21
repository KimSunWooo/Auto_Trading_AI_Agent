"""Horizon mapping. Later phases may add long/short specific policies."""

from ai_investment_agent.horizon.mapping import holding_period_days
from ai_investment_agent.horizon.selector import HorizonSelector

__all__ = ["HorizonSelector", "holding_period_days"]
