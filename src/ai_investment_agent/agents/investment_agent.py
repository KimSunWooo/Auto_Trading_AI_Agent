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
from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import (
    DecisionType,
    EntryTiming,
    Horizon,
    HorizonChoice,
    JournalStage,
    PositionThesisStatus,
    Stance,
)
from ai_investment_agent.domain.ids import new_decision_id
from ai_investment_agent.domain.market import MarketRegime, MarketSnapshot
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.horizon.selector import HorizonSelector
from ai_investment_agent.journal.service import JournalService
from ai_investment_agent.policy.priorities import PRIORITY_ORDER
from ai_investment_agent.policy.utility import UtilityConfig
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


class InvestmentJudgmentAgent:
    """Long and short agents plus horizon selection. Stops at TradeProposal."""

    def __init__(
        self,
        repository: DecisionRepository,
        publisher: DecisionPublisher,
        config: UtilityConfig | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config or UtilityConfig()
        self._long = LongTermAgent(self._config)
        self._short = ShortTermAgent(self._config)
        self._selector = HorizonSelector(self._config)
        self._entry = EntryAnalyzer(self._config)
        self._positions = PositionThesisMonitor()
        self._capital = CapitalPolicy()
        self._engine = DecisionEngine(self._capital)
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

        desired = _desired(selected, position_status)
        thesis = _thesis(request.ticker, long_view, short_view, selected)
        conditions = [
            InvalidationCondition(code=code, description=code.replace("_", " "))
            for code in thesis.invalidations
        ]
        capital = self._capital.resolve(request.capital_context)
        raw_confidence = min(long_view.confidence, short_view.confidence)
        output = self._engine.decide(
            DecisionInput(
                decision_id=decision_id,
                snapshot=request.snapshot,
                events=(),
                regime=request.regime,
                capital=capital,
                thesis=thesis,
                desired_decision=desired,
                raw_confidence=raw_confidence,
                desired_capital_pct=Decimal("5") if desired in {
                    DecisionType.LONG_TERM_BUY,
                    DecisionType.SHORT_TERM_BUY,
                } else Decimal("0"),
                generated_at=now,
                invalidation_conditions=tuple(conditions),
            )
        )
        proposal = output.proposal.model_copy(
            update={"reason_codes": _unique(output.reason_codes + selected.reason_codes)}
        )
        record = DecisionSnapshot(
            decision_id=decision_id,
            ticker=request.ticker,
            market_snapshot=request.snapshot,
            events=[],
            market_regime=request.regime,
            capital_context=capital,
            thesis=thesis,
            proposal=proposal,
            priorities_applied=list(PRIORITY_ORDER),
            created_at=now,
            horizon_decision=selected,
        )
        self._repository.save_snapshot(record)
        self._publisher.publish(proposal)
        self._journal.record(
            decision_id,
            JournalStage.TRADE_PROPOSAL,
            f"Horizon {selected.choice.value} published as TradeProposal.",
            reason_codes=proposal.reason_codes,
        )
        return record


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
