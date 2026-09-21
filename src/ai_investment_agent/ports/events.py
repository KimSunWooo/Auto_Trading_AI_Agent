from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ai_investment_agent.domain.market import MarketEvent


class EventProvider(Protocol):
    def get_events(self, ticker: str) -> Sequence[MarketEvent]:
        """Return market-relevant events. Not bound to a news or DART vendor."""
        ...
