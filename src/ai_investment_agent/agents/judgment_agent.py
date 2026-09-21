from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from ai_investment_agent.capital.policy import CapitalPolicy
from ai_investment_agent.decision.engine import DecisionEngine, DecisionInput
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.confidence import CalibrationTable
from ai_investment_agent.domain.context import MarketContext
from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import (
    DecisionType,
    HorizonChoice,
    JournalStage,
    KillSwitchLevel,
    PolicyState,
)
from ai_investment_agent.domain.ids import new_decision_id
from ai_investment_agent.domain.policy import HumanOverride, PortfolioContext, RiskBudgets
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.domain.versions import PROMPT_VERSION
from ai_investment_agent.intelligence.regime import RegimeAssessor
from ai_investment_agent.journal.service import JournalService
from ai_investment_agent.policy.priorities import PRIORITY_ORDER
from ai_investment_agent.policy.safety import SafetyPolicyLayer
from ai_investment_agent.ports.events import EventProvider
from ai_investment_agent.ports.llm import LlmProvider, LlmRequest
from ai_investment_agent.ports.market_data import MarketDataProvider
from ai_investment_agent.ports.publisher import DecisionPublisher
from ai_investment_agent.ports.repository import DecisionRepository


@dataclass(frozen=True)
class JudgmentRequest:
    ticker: str
    capital_context: CapitalContext | None = None
    portfolio_context: PortfolioContext | None = None
    human_override: HumanOverride | None = None
    risk_budgets: RiskBudgets | None = None
    policy_state: PolicyState = PolicyState.NORMAL
    kill_switch_level: KillSwitchLevel = KillSwitchLevel.LEVEL_0_NORMAL
    feature_snapshot: MarketContext | None = None


class JudgmentAgent:
    """Orchestrates Data → Analysis → Risk → Decision → TradeProposal.

    Stops there. Never constructs an order.
    """

    def __init__(
        self,
        market_data: MarketDataProvider,
        events: EventProvider,
        llm: LlmProvider,
        repository: DecisionRepository,
        publisher: DecisionPublisher,
        now_fn: Callable[[], datetime] | None = None,
        calibration: CalibrationTable | None = None,
    ) -> None:
        self._market_data = market_data
        self._events = events
        self._llm = llm
        self._repository = repository
        self._publisher = publisher
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._capital_policy = CapitalPolicy()
        self._engine = DecisionEngine(self._capital_policy, calibration)
        self._safety = SafetyPolicyLayer()
        self._regime = RegimeAssessor()
        self._journal = JournalService(repository, self._now)

    def judge(self, request: JudgmentRequest) -> DecisionSnapshot:
        now = self._now()
        decision_id = new_decision_id()

        snapshot = self._market_data.get_snapshot(request.ticker)
        self._journal.record(
            decision_id,
            JournalStage.DATA,
            "Loaded market snapshot from MarketDataProvider.",
            payload={"ticker": snapshot.ticker, "source": snapshot.source},
        )

        events = list(self._events.get_events(request.ticker))
        self._journal.record(
            decision_id,
            JournalStage.DATA,
            f"Loaded {len(events)} market event(s) from EventProvider.",
        )

        capital = self._capital_policy.resolve(request.capital_context)
        if not capital.was_provided:
            self._journal.record(
                decision_id,
                JournalStage.DATA,
                "CapitalContext omitted. Conservative zero deployable capital applied.",
                reason_codes=["CAPITAL_CONTEXT_MISSING"],
                payload=capital.model_dump(mode="json"),
            )

        llm_response = self._llm.complete(
            LlmRequest(
                task="investment_thesis",
                ticker=request.ticker,
                payload={
                    "snapshot": snapshot.model_dump(mode="json"),
                    "eventCount": len(events),
                },
            )
        )
        thesis, desired, raw_confidence, desired_pct, conditions = _parse_llm(llm_response.content)
        self._journal.record(
            decision_id,
            JournalStage.ANALYSIS,
            "Parsed fixture LLM thesis. No production model is connected.",
            payload={"modelName": llm_response.model_name, "desiredDecision": desired.value},
        )

        regime = self._regime.assess(snapshot, events, as_of=now)
        self._journal.record(
            decision_id,
            JournalStage.RISK_ASSESSMENT,
            f"Assessed market regime as {regime.regime.value}.",
            payload=regime.model_dump(mode="json"),
        )

        output = self._engine.decide(
            DecisionInput(
                decision_id=decision_id,
                snapshot=snapshot,
                events=tuple(events),
                regime=regime,
                capital=capital,
                thesis=thesis,
                desired_decision=desired,
                raw_confidence=raw_confidence,
                desired_capital_pct=desired_pct,
                generated_at=now,
                invalidation_conditions=tuple(conditions),
            )
        )
        proposal = self._safety.apply(
            output.proposal,
            capital=capital,
            portfolio=request.portfolio_context,
            risk_budgets=request.risk_budgets,
            human=request.human_override,
            policy_state=request.policy_state,
            kill_switch=request.kill_switch_level,
        )
        self._journal.record(
            decision_id,
            JournalStage.DECISION,
            f"Decision resolved to {proposal.decision.value}.",
            reason_codes=proposal.reason_codes,
        )

        record = DecisionSnapshot(
            decision_id=decision_id,
            ticker=request.ticker,
            market_snapshot=snapshot,
            events=events,
            market_regime=regime,
            capital_context=capital,
            thesis=thesis,
            proposal=proposal,
            priorities_applied=list(PRIORITY_ORDER),
            created_at=now,
            selected_horizon=_selected_horizon(proposal),
            feature_snapshot=request.feature_snapshot,
            prompt_version=PROMPT_VERSION,
        )
        self._repository.save_snapshot(record)
        self._publisher.publish(proposal)
        self._journal.record(
            decision_id,
            JournalStage.TRADE_PROPOSAL,
            "Published TradeProposal. No order was created.",
            reason_codes=proposal.reason_codes,
            payload={"decisionId": decision_id, "action": proposal.action.value},
        )
        return record


def _parse_llm(
    content: dict,
) -> tuple[InvestmentThesis, DecisionType, float, Decimal, list[InvalidationCondition]]:
    thesis_raw = content.get("thesis") or {}
    thesis = InvestmentThesis.model_validate(thesis_raw) if thesis_raw else InvestmentThesis(
        headline="Empty fixture thesis",
        summary="LLM adapter returned no thesis body.",
        bull_case="",
        bear_case="",
    )
    desired = DecisionType(content.get("desiredDecision", DecisionType.NO_TRADE.value))
    raw_confidence = float(content.get("rawConfidence", 0.0))
    desired_pct = Decimal(str(content.get("suggestedCapitalPct", "0")))
    conditions = [
        InvalidationCondition.model_validate(item)
        for item in content.get("invalidationConditions", [])
    ]
    return thesis, desired, raw_confidence, desired_pct, conditions


def _selected_horizon(proposal) -> HorizonChoice | None:
    mapping = {
        DecisionType.LONG_TERM_BUY: HorizonChoice.LONG_TERM,
        DecisionType.SHORT_TERM_BUY: HorizonChoice.SHORT_TERM,
        DecisionType.TACTICAL_WAIT: HorizonChoice.TACTICAL_WAIT,
        DecisionType.NO_TRADE: HorizonChoice.NO_TRADE,
    }
    return mapping.get(proposal.decision)
