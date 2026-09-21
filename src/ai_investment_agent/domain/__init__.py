"""Core domain models. This layer has no adapter, SDK, or I/O imports."""

from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import (
    Action,
    AgentPriority,
    DecisionType,
    EventSeverity,
    Horizon,
    JournalStage,
    MarketRegimeType,
    ReasonCode,
)
from ai_investment_agent.domain.journal import DecisionJournalEntry
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.serialization import from_json, to_json
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.domain.versions import FEATURE_VERSION, MODEL_VERSION, POLICY_VERSION

__all__ = [
    "Action",
    "AgentPriority",
    "CapitalContext",
    "DecisionJournalEntry",
    "DecisionSnapshot",
    "DecisionType",
    "EventSeverity",
    "FEATURE_VERSION",
    "Horizon",
    "InvalidationCondition",
    "InvestmentThesis",
    "JournalStage",
    "MODEL_VERSION",
    "MarketEvent",
    "MarketRegime",
    "MarketRegimeType",
    "MarketSnapshot",
    "POLICY_VERSION",
    "ReasonCode",
    "TradeProposal",
    "from_json",
    "to_json",
]
