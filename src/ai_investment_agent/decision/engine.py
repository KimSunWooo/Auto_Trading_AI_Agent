from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ai_investment_agent.capital.policy import CapitalPolicy
from ai_investment_agent.domain.agent_views import AgentAssessment
from ai_investment_agent.domain.confidence import CalibrationTable
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import Action, DataMode, DecisionType, Horizon, ReasonCode
from ai_investment_agent.domain.market import MarketEvent, MarketRegime, MarketSnapshot
from ai_investment_agent.domain.proposal import (
    TradeProposal,
    action_horizon_for,
)
from ai_investment_agent.domain.thesis import InvalidationCondition, InvestmentThesis
from ai_investment_agent.domain.versions import FEATURE_VERSION, MODEL_VERSION, POLICY_VERSION, PROMPT_VERSION
from ai_investment_agent.horizon.mapping import holding_period_days
from ai_investment_agent.policy.calibration import resolve_calibrated
from ai_investment_agent.policy.freshness import ProposalFreshnessPolicy
from ai_investment_agent.policy.gates import apply_hard_gates
from ai_investment_agent.policy.priorities import PRIORITY_ORDER


@dataclass(frozen=True)
class DecisionInput:
    decision_id: str
    snapshot: MarketSnapshot
    events: tuple[MarketEvent, ...]
    regime: MarketRegime
    capital: CapitalContext
    thesis: InvestmentThesis
    desired_decision: DecisionType
    raw_confidence: float
    desired_capital_pct: Decimal
    generated_at: datetime
    invalidation_conditions: tuple[InvalidationCondition, ...] = ()
    long_assessment: AgentAssessment | None = None
    short_assessment: AgentAssessment | None = None
    data_mode: DataMode = DataMode.FIXTURE
    analysis_as_of: datetime | None = None
    context_fingerprint: str | None = None
    freshness: ProposalFreshnessPolicy | None = None


@dataclass(frozen=True)
class DecisionOutput:
    proposal: TradeProposal
    decision: DecisionType
    reason_codes: list[str] = field(default_factory=list)


class DecisionEngine:
    """Pure judgment. No I/O, no broker, no order objects."""

    def __init__(
        self,
        capital_policy: CapitalPolicy | None = None,
        calibration: CalibrationTable | None = None,
    ) -> None:
        self._capital_policy = capital_policy or CapitalPolicy()
        self._calibration = calibration

    def decide(self, payload: DecisionInput) -> DecisionOutput:
        gate = apply_hard_gates(
            payload.desired_decision,
            payload.regime,
            payload.capital,
            payload.snapshot,
        )
        decision = gate.decision
        action, horizon = action_horizon_for(decision)
        reasons = list(gate.reason_codes)

        suggested_pct, cap_reasons = self._capital_policy.cap_suggested_pct(
            payload.desired_capital_pct,
            payload.capital,
            action,
        )
        reasons.extend(cap_reasons)

        if action is Action.BUY and suggested_pct <= 0:
            decision = DecisionType.NO_TRADE
            action, horizon = Action.NO_TRADE, Horizon.NONE
            suggested_pct = Decimal("0")
            reasons.append(ReasonCode.ZERO_DEPLOYABLE_CAPITAL.value)
            reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)

        if decision is DecisionType.NO_TRADE and ReasonCode.POLICY_NO_TRADE_IS_VALID.value not in reasons:
            reasons.append(ReasonCode.POLICY_NO_TRADE_IS_VALID.value)

        calibrated = resolve_calibrated(payload.raw_confidence, self._calibration)
        expected_return, estimated_risk, metric_reasons = _risk_return(decision, payload)
        reasons.extend(metric_reasons)
        analysis_as_of = payload.analysis_as_of or payload.snapshot.as_of
        freshness = payload.freshness or ProposalFreshnessPolicy()
        valid_until = freshness.valid_until(generated_at=payload.generated_at, horizon=horizon)

        proposal = TradeProposal(
            decision_id=payload.decision_id,
            ticker=payload.snapshot.ticker,
            horizon=horizon,
            action=action,
            raw_confidence=payload.raw_confidence,
            calibrated_confidence=calibrated,
            expected_return=expected_return,
            estimated_risk=estimated_risk,
            suggested_capital_pct=suggested_pct,
            expected_holding_period=holding_period_days(horizon),
            thesis=payload.thesis,
            invalidation_conditions=list(payload.invalidation_conditions),
            reason_codes=_unique(reasons),
            market_regime=payload.regime,
            model_version=MODEL_VERSION,
            prompt_version=PROMPT_VERSION,
            feature_version=FEATURE_VERSION,
            policy_version=POLICY_VERSION,
            generated_at=payload.generated_at,
            data_mode=payload.data_mode,
            analysis_as_of=analysis_as_of,
            valid_until=valid_until,
            context_fingerprint=payload.context_fingerprint,
            metric_source=metric_reasons[0] if metric_reasons else None,
        )
        # PRIORITY_ORDER is recorded by the agent on the snapshot, not on the proposal.
        _ = PRIORITY_ORDER
        return DecisionOutput(proposal=proposal, decision=decision, reason_codes=proposal.reason_codes)


def _risk_return(
    decision: DecisionType, payload: DecisionInput
) -> tuple[Decimal, Decimal, list[str]]:
    if decision in {DecisionType.NO_TRADE, DecisionType.TACTICAL_WAIT}:
        return Decimal("0"), Decimal("0"), []
    if decision in {DecisionType.EXIT_REVIEW, DecisionType.HOLD, DecisionType.SELL}:
        return Decimal("0"), payload.snapshot.volatility or Decimal("0"), []
    vol = payload.snapshot.volatility or Decimal("0.05")
    if decision is DecisionType.SHORT_TERM_BUY:
        return _from_assessment(
            payload.short_assessment,
            fallback_return=Decimal("0.02"),
            fallback_risk=vol,
            source=ReasonCode.METRICS_FROM_SHORT_AGENT,
        )
    if decision is DecisionType.LONG_TERM_BUY:
        return _from_assessment(
            payload.long_assessment,
            fallback_return=Decimal("0.06"),
            fallback_risk=vol,
            source=ReasonCode.METRICS_FROM_LONG_AGENT,
        )
    return Decimal("0"), vol, []


def _from_assessment(
    assessment: AgentAssessment | None,
    *,
    fallback_return: Decimal,
    fallback_risk: Decimal,
    source: ReasonCode,
) -> tuple[Decimal, Decimal, list[str]]:
    if assessment is None:
        return fallback_return, fallback_risk, [ReasonCode.METRICS_FALLBACK_HEURISTIC.value]
    utility = assessment.utility
    expected = utility.expected_return if utility.expected_return is not None else Decimal("0")
    risk = utility.risk_penalty + utility.tail_risk + utility.drawdown_penalty
    if risk < 0:
        risk = Decimal("0")
    return expected, risk, [source.value]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
