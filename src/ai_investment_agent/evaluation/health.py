"""Model health from journaled judgments. UNKNOWN is never HEALTHY."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from math import sqrt
from statistics import mean, pstdev

from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import Action, ModelHealthStatus
from ai_investment_agent.domain.evaluation import ModelHealthMetrics

MIN_OUTCOME_SAMPLE = 5


class ModelHealthAssessor:
    def assess(self, snapshots: Sequence[DecisionSnapshot]) -> ModelHealthMetrics:
        records = list(snapshots)
        distribution = Counter(snap.proposal.action.value for snap in records)
        raw_scores = [snap.proposal.raw_confidence for snap in records]
        measured = [snap for snap in records if snap.counterfactual.is_measured]
        directional = [
            snap
            for snap in measured
            if snap.proposal.action in {Action.BUY, Action.SELL}
            and snap.counterfactual.return_1d is not None
        ]
        wins = 0
        signed_returns: list[Decimal] = []
        for snap in directional:
            ret = snap.counterfactual.return_1d
            if ret is None:
                continue
            signed = ret if snap.proposal.action is Action.BUY else -ret
            signed_returns.append(signed)
            if signed > 0:
                wins += 1

        win_rate = (wins / len(signed_returns)) if signed_returns else None
        expected_value = (
            Decimal(str(mean(signed_returns))) if signed_returns else None
        )
        drawdown = _max_drawdown(signed_returns) if signed_returns else None
        sharpe = _sharpe(signed_returns) if signed_returns else None
        calibration_error = _calibration_error(measured)
        frequency = float(len(records)) if records else None
        average_confidence = mean(raw_scores) if raw_scores else None

        metrics = ModelHealthMetrics(
            win_rate=win_rate,
            expected_value=expected_value,
            drawdown=drawdown,
            sharpe=sharpe,
            calibration_error=calibration_error,
            decision_distribution=dict(distribution),
            proposal_frequency=frequency,
            average_confidence=average_confidence,
            sample_size=len(records),
            outcome_sample_size=len(signed_returns),
            status=ModelHealthStatus.UNKNOWN,
        )
        return metrics.model_copy(update={"status": _status(metrics)})


def _status(metrics: ModelHealthMetrics) -> ModelHealthStatus:
    if metrics.sample_size == 0 or metrics.outcome_sample_size < MIN_OUTCOME_SAMPLE:
        return ModelHealthStatus.UNKNOWN
    if metrics.win_rate is None or metrics.drawdown is None:
        return ModelHealthStatus.UNKNOWN
    if metrics.win_rate < 0.40 or metrics.drawdown > Decimal("0.20"):
        return ModelHealthStatus.UNHEALTHY
    if metrics.win_rate < 0.50 or metrics.drawdown > Decimal("0.10"):
        return ModelHealthStatus.DEGRADED
    return ModelHealthStatus.HEALTHY


def _max_drawdown(returns: list[Decimal]) -> Decimal:
    equity = Decimal("0")
    peak = Decimal("0")
    worst = Decimal("0")
    for ret in returns:
        equity += ret
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > worst:
            worst = dd
    return worst


def _sharpe(returns: list[Decimal]) -> float | None:
    if len(returns) < 2:
        return None
    values = [float(item) for item in returns]
    sigma = pstdev(values)
    if sigma == 0:
        return None
    return mean(values) / sigma * sqrt(len(values))


def _calibration_error(measured: Sequence[DecisionSnapshot]) -> float | None:
    pairs: list[tuple[float, float]] = []
    for snap in measured:
        calibrated = snap.proposal.calibrated_confidence
        ret = snap.counterfactual.return_1d
        if calibrated is None or ret is None:
            continue
        realized = 1.0 if ret > 0 else 0.0
        pairs.append((calibrated, realized))
    if not pairs:
        return None
    return mean(abs(pred - real) for pred, real in pairs)
