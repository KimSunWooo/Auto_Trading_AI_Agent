from __future__ import annotations

from typing import Protocol

from ai_investment_agent.domain.proposal import TradeProposal


class DecisionPublisher(Protocol):
    """Publishes a TradeProposal for later consumption.

    Implementations must not place orders, call a broker, or notify
    an auto-trading system in this project.
    """

    def publish(self, proposal: TradeProposal) -> None:
        ...
