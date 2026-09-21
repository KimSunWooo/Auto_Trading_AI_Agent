"""Replay a stored judgment by decisionId.

Full deterministic re-execution of live LLM/market calls is not claimed.
This restores the recorded inputs and version pins exactly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ai_investment_agent.domain.agent_views import AgentAssessment
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.context import MarketContext
from ai_investment_agent.domain.enums import DataMode, HorizonChoice
from ai_investment_agent.domain.errors import DecisionNotFoundError
from ai_investment_agent.domain.evaluation import CounterfactualOutcome, VersionPin
from ai_investment_agent.domain.journal import DecisionJournalEntry, DecisionRecord
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.thesis import InvestmentThesis
from ai_investment_agent.ports.repository import DecisionRepository


class ReplayBundle(DomainModel):
    """Inputs and versions as they were at judgment time."""

    decision_id: str = Field(min_length=1)
    timestamp: datetime
    ticker: str
    market_snapshot: MarketSnapshot
    event_snapshot: list[MarketEvent] = Field(default_factory=list)
    feature_snapshot: MarketContext | None = None
    market_regime: MarketRegime
    capital_context: CapitalContext
    long_analysis: AgentAssessment | None = None
    short_analysis: AgentAssessment | None = None
    selected_horizon: HorizonChoice | None = None
    thesis: InvestmentThesis
    proposal: TradeProposal
    versions: VersionPin
    journal: list[DecisionJournalEntry] = Field(default_factory=list)
    counterfactual: CounterfactualOutcome = Field(default_factory=CounterfactualOutcome)
    record: DecisionRecord
    deterministic_rerun: bool = False
    data_mode: DataMode = DataMode.FIXTURE
    restore_note: str = (
        "Recorded inputs and version pins restored. "
        "Live model and market calls are not re-executed."
    )


class ReplayService:
    def __init__(self, repository: DecisionRepository) -> None:
        self._repository = repository

    def replay(self, decision_id: str) -> ReplayBundle:
        snapshot = self._repository.get_snapshot(decision_id)
        if snapshot is None:
            raise DecisionNotFoundError(decision_id)
        record = snapshot.to_record()
        return ReplayBundle(
            decision_id=snapshot.decision_id,
            timestamp=snapshot.created_at,
            ticker=snapshot.ticker,
            market_snapshot=snapshot.market_snapshot,
            event_snapshot=list(snapshot.events),
            feature_snapshot=snapshot.feature_snapshot,
            market_regime=snapshot.market_regime,
            capital_context=snapshot.capital_context,
            long_analysis=snapshot.long_analysis,
            short_analysis=snapshot.short_analysis,
            selected_horizon=snapshot.selected_horizon,
            thesis=snapshot.thesis,
            proposal=snapshot.proposal,
            versions=record.versions,
            journal=list(self._repository.list_journal(decision_id)),
            counterfactual=snapshot.counterfactual,
            record=record,
            data_mode=snapshot.data_mode,
            deterministic_rerun=False,
        )
