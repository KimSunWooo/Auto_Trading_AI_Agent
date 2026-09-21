from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ai_investment_agent.domain.agent_views import AgentAssessment, HorizonDecision
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.confidence import ConfidenceAssessment
from ai_investment_agent.domain.context import MarketContext
from ai_investment_agent.domain.enums import Action, AgentPriority, DataMode, HorizonChoice
from ai_investment_agent.domain.evaluation import CounterfactualOutcome
from ai_investment_agent.domain.journal import DecisionRecord
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.runtime import DecisionReadiness, ProviderStatus
from ai_investment_agent.domain.thesis import InvestmentThesis
from ai_investment_agent.domain.versions import PROMPT_VERSION


class DecisionSnapshot(DomainModel):
    """Immutable record of one judgment cycle.

    Stops at TradeProposal. There is no order field by design.
    Stores BUY, SELL, HOLD, TACTICAL_WAIT, NO_TRADE, and EXIT_REVIEW equally.
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
    horizon_decision: HorizonDecision | None = None
    long_analysis: AgentAssessment | None = None
    short_analysis: AgentAssessment | None = None
    selected_horizon: HorizonChoice | None = None
    feature_snapshot: MarketContext | None = None
    prompt_version: str = PROMPT_VERSION
    counterfactual: CounterfactualOutcome = Field(default_factory=CounterfactualOutcome)
    data_mode: DataMode = DataMode.FIXTURE
    analysis_as_of: datetime | None = None
    valid_until: datetime | None = None
    context_fingerprint: str | None = None
    readiness: DecisionReadiness | None = None
    provider_health: list[ProviderStatus] = Field(default_factory=list)
    confidence_assessment: ConfidenceAssessment | None = None

    @property
    def timestamp(self) -> datetime:
        return self.created_at

    @property
    def event_snapshot(self) -> list[MarketEvent]:
        return self.events

    @property
    def action(self) -> Action:
        return self.proposal.action

    def to_record(self) -> DecisionRecord:
        proposal = self.proposal
        return DecisionRecord(
            decision_id=self.decision_id,
            timestamp=self.created_at,
            ticker=self.ticker,
            market_snapshot=self.market_snapshot,
            event_snapshot=list(self.events),
            feature_snapshot=self.feature_snapshot,
            market_regime=self.market_regime,
            long_analysis=self.long_analysis,
            short_analysis=self.short_analysis,
            selected_horizon=self.selected_horizon,
            action=proposal.action,
            raw_confidence=proposal.raw_confidence,
            calibrated_confidence=proposal.calibrated_confidence,
            expected_return=proposal.expected_return,
            estimated_risk=proposal.estimated_risk,
            suggested_capital_pct=proposal.suggested_capital_pct,
            reason_codes=list(proposal.reason_codes),
            thesis=self.thesis,
            invalidation_conditions=list(proposal.invalidation_conditions),
            model_version=proposal.model_version,
            prompt_version=self.prompt_version,
            feature_version=proposal.feature_version,
            policy_version=proposal.policy_version,
            counterfactual=self.counterfactual,
        )
