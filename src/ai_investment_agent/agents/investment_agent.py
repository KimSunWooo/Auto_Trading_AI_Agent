from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from ai_investment_agent.agents.long_term import LongTermAgent
from ai_investment_agent.agents.short_term import ShortTermAgent
from ai_investment_agent.capital.policy import CapitalPolicy
from ai_investment_agent.decision.engine import DecisionEngine, DecisionInput
from ai_investment_agent.decision.entry import EntryAnalyzer
from ai_investment_agent.decision.position_monitor import PositionThesisMonitor
from ai_investment_agent.domain.agent_views import (
    EntrySnapshot,
    FixturePosition,
    HorizonDecision,
    LongTermFeatures,
    ShortTermFeatures,
)
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.confidence import CalibrationTable, compose_confidence
from ai_investment_agent.domain.context import MarketContext
from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import (
    DataMode,
    DecisionType,
    EntryTiming,
    Horizon,
    HorizonChoice,
    JournalStage,
    KillSwitchLevel,
    PositionThesisStatus,
    PolicyState,
    ReasonCode,
    Stance,
)
from ai_investment_agent.domain.fingerprint import context_fingerprint
from ai_investment_agent.domain.ids import new_decision_id
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.policy import HumanOverride, PortfolioContext, RiskBudgets
from ai_investment_agent.domain.runtime import DecisionReadiness
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.domain.versions import MODEL_VERSION, PROMPT_VERSION
from ai_investment_agent.horizon.selector import HorizonSelector
from ai_investment_agent.journal.service import JournalService
from ai_investment_agent.policy.priorities import PRIORITY_ORDER
from ai_investment_agent.policy.safety import SafetyPolicyLayer
from ai_investment_agent.policy.utility import UtilityConfig
from ai_investment_agent.ports.llm import LlmResponse
from ai_investment_agent.ports.publisher import DecisionPublisher
from ai_investment_agent.ports.repository import DecisionRepository


@dataclass(frozen=True)
class InvestmentJudgmentRequest:
    ticker: str
    snapshot: MarketSnapshot
    regime: MarketRegime
    long_features: LongTermFeatures
    short_features: ShortTermFeatures
    capital_context: CapitalContext | None = None
    entry: EntrySnapshot | None = None
    position: FixturePosition | None = None
    portfolio_context: PortfolioContext | None = None
    human_override: HumanOverride | None = None
    risk_budgets: RiskBudgets | None = None
    policy_state: PolicyState = PolicyState.NORMAL
    kill_switch_level: KillSwitchLevel = KillSwitchLevel.LEVEL_0_NORMAL
    feature_snapshot: MarketContext | None = None
    events: tuple[MarketEvent, ...] = ()
    data_mode: DataMode = DataMode.FIXTURE
    readiness: DecisionReadiness | None = None
    llm_assist: LlmResponse | None = None


class InvestmentJudgmentAgent:
    """Long and short agents plus horizon selection. Stops at TradeProposal."""

    def __init__(
        self,
        repository: DecisionRepository,
        publisher: DecisionPublisher,
        config: UtilityConfig | None = None,
        now_fn: Callable[[], datetime] | None = None,
        calibration: CalibrationTable | None = None,
    ) -> None:
        self._config = config or UtilityConfig()
        self._long = LongTermAgent(self._config)
        self._short = ShortTermAgent(self._config)
        self._selector = HorizonSelector(self._config)
        self._entry = EntryAnalyzer(self._config)
        self._positions = PositionThesisMonitor()
        self._capital = CapitalPolicy()
        self._engine = DecisionEngine(self._capital, calibration)
        self._safety = SafetyPolicyLayer()
        self._repository = repository
        self._publisher = publisher
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._journal = JournalService(repository, self._now)

    def judge(self, request: InvestmentJudgmentRequest) -> DecisionSnapshot:
        now = self._now()
        decision_id = new_decision_id()
        long_view = self._long.assess(request.long_features)
        short_view = self._short.assess(request.short_features)
        self._journal.record(
            decision_id,
            JournalStage.ANALYSIS,
            "Long and short agents scored independently.",
            payload={
                "longStance": long_view.stance.value,
                "shortStance": short_view.stance.value,
                "longNetEdge": _num(long_view.net_edge),
                "shortNetEdge": _num(short_view.net_edge),
            },
        )

        selected = self._selector.select(long_view, short_view, request.regime)
        timing, entry_reasons = self._entry.timing(selected.choice, request.entry)
        position_status = self._positions.inspect(request.position)
        selected = selected.model_copy(
            update={
                "entry_timing": timing,
                "position_status": position_status,
                "reason_codes": _unique(list(selected.reason_codes) + entry_reasons),
            }
        )
        if timing is EntryTiming.WAIT and selected.choice in {
            HorizonChoice.LONG_TERM,
            HorizonChoice.SHORT_TERM,
        }:
            selected = selected.model_copy(update={"choice": HorizonChoice.TACTICAL_WAIT})

        readiness = request.readiness
        live_compatible = request.data_mode in {
            DataMode.LIVE_OBSERVATION,
            DataMode.LIVE_SHADOW,
        }
        if readiness is not None and not readiness.allows_new_buy:
            selected = _block_new_buy(
                selected,
                list(readiness.reason_codes) or [ReasonCode.DECISION_READINESS_BLOCKED.value],
            )
        elif readiness is None and live_compatible:
            selected = _block_new_buy(
                selected,
                [
                    ReasonCode.DECISION_READINESS_BLOCKED.value,
                    ReasonCode.POLICY_UNKNOWN_NO_NEW_BUY.value,
                ],
            )

        desired = _desired(selected, position_status)
        thesis = _thesis(request.ticker, long_view, short_view, selected)
        thesis, selected, desired, llm_failed, prompt_version, model_version = _apply_llm_assist(
            request,
            thesis=thesis,
            selected=selected,
            desired=desired,
        )
        conditions = [
            InvalidationCondition(code=code, description=code.replace("_", " "))
            for code in thesis.invalidations
        ]
        capital = self._capital.resolve(request.capital_context)
        event_uncertainty = 0.0
        if request.feature_snapshot is not None:
            event_uncertainty = 1.0 - request.feature_snapshot.event_features.event_confidence
        assessment = compose_confidence(
            selected_choice=selected.choice,
            long_view=long_view,
            short_view=short_view,
            data_quality=float(request.snapshot.data_completeness),
            market_regime_confidence=request.regime.confidence,
            event_uncertainty=event_uncertainty,
        )
        fingerprint = context_fingerprint(
            ticker=request.ticker,
            analysis_as_of=request.snapshot.as_of,
            event_ids=[event.event_id for event in request.events],
            last_price=request.snapshot.last_price,
            data_mode=request.data_mode,
        )
        output = self._engine.decide(
            DecisionInput(
                decision_id=decision_id,
                snapshot=request.snapshot,
                events=(),
                regime=request.regime,
                capital=capital,
                thesis=thesis,
                desired_decision=desired,
                raw_confidence=assessment.raw_confidence,
                desired_capital_pct=Decimal("5") if desired in {
                    DecisionType.LONG_TERM_BUY,
                    DecisionType.SHORT_TERM_BUY,
                } else Decimal("0"),
                generated_at=now,
                invalidation_conditions=tuple(conditions),
                long_assessment=long_view,
                short_assessment=short_view,
                data_mode=request.data_mode,
                analysis_as_of=request.snapshot.as_of,
                context_fingerprint=fingerprint,
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
            data_mode=request.data_mode,
        )
        if proposal.calibrated_confidence is not None:
            assessment = assessment.model_copy(
                update={
                    "calibrated_confidence": proposal.calibrated_confidence,
                    "calibration_applied": True,
                }
            )
        proposal = proposal.model_copy(
            update={
                "reason_codes": _unique(proposal.reason_codes + selected.reason_codes),
                "prompt_version": prompt_version,
                "model_version": model_version,
                "thesis": thesis,
            }
        )
        record = DecisionSnapshot(
            decision_id=decision_id,
            ticker=request.ticker,
            market_snapshot=request.snapshot,
            events=list(request.events),
            market_regime=request.regime,
            capital_context=capital,
            thesis=thesis,
            proposal=proposal,
            priorities_applied=list(PRIORITY_ORDER),
            created_at=now,
            horizon_decision=selected,
            long_analysis=long_view,
            short_analysis=short_view,
            selected_horizon=selected.choice,
            feature_snapshot=request.feature_snapshot,
            prompt_version=prompt_version,
            data_mode=request.data_mode,
            analysis_as_of=request.snapshot.as_of,
            valid_until=proposal.valid_until,
            context_fingerprint=fingerprint,
            readiness=readiness,
            confidence_assessment=assessment,
        )
        self._repository.save_snapshot(record)
        self._publisher.publish(proposal)
        self._journal.record(
            decision_id,
            JournalStage.ANALYSIS,
            "LLM assist applied" if request.llm_assist is not None else "LLM assist not used",
            reason_codes=[ReasonCode.LLM_FAILED.value] if llm_failed else [],
            payload={
                "llmCalled": request.llm_assist is not None,
                "llmFailed": llm_failed,
                "modelVersion": model_version,
                "promptVersion": prompt_version,
                "llmStatus": (
                    request.llm_assist.content.get("llmStatus") if request.llm_assist else None
                ),
            },
        )
        self._journal.record(
            decision_id,
            JournalStage.TRADE_PROPOSAL,
            f"Horizon {selected.choice.value} published as TradeProposal.",
            reason_codes=proposal.reason_codes,
        )
        return record


def _block_new_buy(selected: HorizonDecision, extra_reasons: list[str]) -> HorizonDecision:
    if selected.choice not in {HorizonChoice.LONG_TERM, HorizonChoice.SHORT_TERM}:
        return selected.model_copy(
            update={"reason_codes": _unique(list(selected.reason_codes) + extra_reasons)}
        )
    return selected.model_copy(
        update={
            "choice": HorizonChoice.TACTICAL_WAIT,
            "reason_codes": _unique(list(selected.reason_codes) + extra_reasons),
        }
    )


def _desired(selected: HorizonDecision, position_status: PositionThesisStatus) -> DecisionType:
    if position_status is PositionThesisStatus.EXIT_REVIEW:
        return DecisionType.EXIT_REVIEW
    if selected.choice is HorizonChoice.NO_TRADE:
        return DecisionType.NO_TRADE
    if selected.choice is HorizonChoice.TACTICAL_WAIT:
        return DecisionType.TACTICAL_WAIT
    if selected.choice is HorizonChoice.LONG_TERM:
        return DecisionType.LONG_TERM_BUY
    return DecisionType.SHORT_TERM_BUY


def _apply_llm_assist(
    request: InvestmentJudgmentRequest,
    *,
    thesis: InvestmentThesis,
    selected: HorizonDecision,
    desired: DecisionType,
) -> tuple[InvestmentThesis, HorizonDecision, DecisionType, bool, str, str]:
    """Use LLM for thesis/risk text only. Failure is fail-closed NO_TRADE.

    desiredDecision from the model never bypasses readiness, capital, or policy.
    """
    assist = request.llm_assist
    if assist is None:
        return thesis, selected, desired, False, PROMPT_VERSION, MODEL_VERSION
    content = assist.content or {}
    status = str(content.get("llmStatus") or content.get("llm_status") or "")
    prompt_version = str(content.get("promptVersion") or content.get("prompt_version") or PROMPT_VERSION)
    model_version = assist.model_name or MODEL_VERSION
    failed = status == "LLM_FAILED" or str(model_version).endswith("/failed")
    if failed:
        selected = selected.model_copy(
            update={
                "choice": HorizonChoice.NO_TRADE,
                "reason_codes": _unique(
                    list(selected.reason_codes) + [ReasonCode.LLM_FAILED.value]
                ),
            }
        )
        thesis = InvestmentThesis(
            headline=str((content.get("thesis") or {}).get("headline") or "LLM unavailable"),
            summary=str(
                (content.get("thesis") or {}).get("summary")
                or "LLM_FAILED. Fail-closed — no fabricated buy."
            ),
            bull_case="Not evaluated.",
            bear_case="Model output unavailable; capital preservation preferred.",
            time_horizon=Horizon.NONE,
            risks=["LLM_FAILED"],
            invalidation_summary="Invalidate any prior LLM-assisted thesis.",
        )
        return thesis, selected, DecisionType.NO_TRADE, True, prompt_version, model_version

    raw_thesis = content.get("thesis") or {}
    if isinstance(raw_thesis, dict):
        updates = {}
        if raw_thesis.get("headline"):
            updates["headline"] = str(raw_thesis["headline"])
        if raw_thesis.get("summary"):
            updates["summary"] = str(raw_thesis["summary"])
        if raw_thesis.get("bullCase") or raw_thesis.get("bull_case"):
            updates["bull_case"] = str(raw_thesis.get("bullCase") or raw_thesis.get("bull_case"))
        if raw_thesis.get("bearCase") or raw_thesis.get("bear_case"):
            updates["bear_case"] = str(raw_thesis.get("bearCase") or raw_thesis.get("bear_case"))
        if updates:
            thesis = thesis.model_copy(update=updates)
    # desiredDecision is advisory text context only — never applied here.
    return thesis, selected, desired, False, prompt_version, model_version


def _thesis(ticker: str, long_view, short_view, selected: HorizonDecision) -> InvestmentThesis:
    drivers = list(long_view.drivers)
    invalidations = _merge(long_view.invalidations, LONG_WATCH_INVALIDATIONS)
    if selected.choice is HorizonChoice.SHORT_TERM:
        drivers = list(short_view.drivers)
        invalidations = _merge(short_view.invalidations, SHORT_WATCH_INVALIDATIONS)
    elif selected.choice is HorizonChoice.TACTICAL_WAIT and long_view.stance is Stance.BULLISH:
        drivers = list(long_view.drivers)
        invalidations = _merge(
            list(long_view.invalidations) + list(short_view.invalidations),
            LONG_WATCH_INVALIDATIONS,
        )
    headline = f"{ticker} {selected.choice.value}"
    summary = (
        f"Long {long_view.stance.value}, short {short_view.stance.value}. "
        "Scores were not averaged."
    )
    horizon = Horizon.NONE
    if selected.choice is HorizonChoice.LONG_TERM:
        horizon = Horizon.LONG_TERM
    elif selected.choice is HorizonChoice.SHORT_TERM:
        horizon = Horizon.SHORT_TERM
    elif selected.choice is HorizonChoice.TACTICAL_WAIT and long_view.stance is Stance.BULLISH:
        horizon = Horizon.LONG_TERM
    return InvestmentThesis(
        headline=headline,
        summary=summary,
        bull_case=", ".join(drivers) or "none",
        bear_case=", ".join(invalidations) or "none",
        time_horizon=horizon,
        catalysts=list(drivers),
        risks=list(invalidations),
        drivers=drivers,
        invalidations=invalidations,
        invalidation_summary="; ".join(invalidations),
    )


def _num(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


LONG_WATCH_INVALIDATIONS = (
    "earnings_downgrade",
    "sector_breakdown",
    "ma_breakdown",
)
SHORT_WATCH_INVALIDATIONS = (
    "intraday_trend_down",
    "short_momentum_down",
    "low_liquidity",
)


def _merge(current: list[str], watches: tuple[str, ...]) -> list[str]:
    return _unique(list(current) + list(watches))


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen
