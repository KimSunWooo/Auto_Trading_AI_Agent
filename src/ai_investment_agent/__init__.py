"""Standalone AI investment judgment agent.

This package's terminal artifact is TradeProposal.
It never places orders, never talks to a broker, and never imports
an auto-trading system.
"""

from ai_investment_agent.domain.versions import (
    FEATURE_VERSION,
    MODEL_VERSION,
    POLICY_VERSION,
)

__version__ = MODEL_VERSION

__all__ = [
    "FEATURE_VERSION",
    "MODEL_VERSION",
    "POLICY_VERSION",
    "__version__",
]
