from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import AgentPriority
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.thesis import InvestmentThesis


class DecisionSnapshot(DomainModel):
    """Immutable record of one judgment cycle.

    Stops at TradeProposal. There is no order field by design.
    """

    decision_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    market_snapshot: MarketSnapshot
    events: list[MarketEvent] = Field(default_factory=list)
    market_regime: MarketRegime
    capital_context: CapitalContext
    thesis: InvestmentThesis
    proposal: TradeProposal
    priorities_applied: list[AgentPriority] = Field(default_factory=list)
    created_at: datetime
