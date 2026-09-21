from __future__ import annotations

from typing import Protocol

from ai_investment_agent.domain.market import MarketSnapshot


class MarketDataProvider(Protocol):
    def get_snapshot(self, ticker: str) -> MarketSnapshot:
        """Return the latest known snapshot. Implementations may be fixtures."""
        ...
