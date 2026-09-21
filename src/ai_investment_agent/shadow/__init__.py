"""Shadow trading layer. Virtual fills only; never a live broker path."""

from ai_investment_agent.shadow.executor import ShadowExecutor
from ai_investment_agent.shadow.performance import ShadowPerformanceReport, ShadowPerformanceTracker
from ai_investment_agent.shadow.service import ShadowTradingService

__all__ = [
    "ShadowExecutor",
    "ShadowPerformanceReport",
    "ShadowPerformanceTracker",
    "ShadowTradingService",
]
