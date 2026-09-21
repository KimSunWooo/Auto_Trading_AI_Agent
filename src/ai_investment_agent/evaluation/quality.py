"""Offline quality scores. Execution Quality is not implemented."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from statistics import mean

from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import Action, EvaluationStatus, QualityAxis
from ai_investment_agent.domain.evaluation import OfflineEvaluationReport, QualityScore

MIN_SAMPLE = 5


class QualityEvaluator:
    """Scores judgment quality axes from journal + counterfactuals.

    Does not score Execution Quality. That axis exists only after a
    broker is connected and is out of scope for this phase.
    """

    def evaluate(
        self,
        snapshots: Sequence[DecisionSnapshot],
        *,
        now: datetime | None = None,
    ) -> OfflineEvaluationReport:
        records = list(snapshots)
        returns = [
            snap.counterfactual.return_1d
            for snap in records
            if snap.counterfactual.is_measured and snap.counterfactual.return_1d is not None
        ]
        return OfflineEvaluationReport(
            alpha=_score(QualityAxis.ALPHA_QUALITY, returns),
            horizon_selection=_horizon_score(records),
            risk_assessment=_risk_score(records),
            capital_allocation=_capital_score(records),
            evaluated_at=now or datetime.now(timezone.utc),
        )


def _score(axis: QualityAxis, values: list[Decimal]) -> QualityScore:
    if len(values) < MIN_SAMPLE:
        return QualityScore(
            axis=axis,
            status=EvaluationStatus.INSUFFICIENT_SAMPLE,
            sample_size=len(values),
        )
    avg = mean(values)
    return QualityScore(
        axis=axis,
        status=EvaluationStatus.SCORED,
        score=Decimal(str(avg)),
        sample_size=len(values),
    )


def _horizon_score(records: Sequence[DecisionSnapshot]) -> QualityScore:
    labeled = [snap for snap in records if snap.selected_horizon is not None]
    measured = [
        snap.counterfactual.return_1d
        for snap in labeled
        if snap.counterfactual.is_measured and snap.counterfactual.return_1d is not None
    ]
    return _score(QualityAxis.HORIZON_SELECTION_QUALITY, measured)


def _risk_score(records: Sequence[DecisionSnapshot]) -> QualityScore:
    gaps: list[Decimal] = []
    for snap in records:
        mae = snap.counterfactual.mae
        if not snap.counterfactual.is_measured or mae is None:
            continue
        estimated = snap.proposal.estimated_risk
        gaps.append(estimated - mae)
    return _score(QualityAxis.RISK_ASSESSMENT_QUALITY, gaps)


def _capital_score(records: Sequence[DecisionSnapshot]) -> QualityScore:
    values: list[Decimal] = []
    for snap in records:
        if snap.proposal.action is not Action.BUY:
            continue
        if not snap.counterfactual.is_measured or snap.counterfactual.return_1d is None:
            continue
        pct = snap.proposal.suggested_capital_pct
        values.append(snap.counterfactual.return_1d * (pct / Decimal("100")))
    return _score(QualityAxis.CAPITAL_ALLOCATION_QUALITY, values)
