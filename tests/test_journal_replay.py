from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ai_investment_agent.agents.judgment_agent import JudgmentRequest
from ai_investment_agent.domain.confidence import CalibrationTable
from ai_investment_agent.domain.enums import (
    Action,
    DecisionType,
    EvaluationStatus,
    ModelHealthStatus,
    ModelLifecycleStage,
    QualityAxis,
)
from ai_investment_agent.domain.errors import DecisionNotFoundError, OnlineLearningForbiddenError
from ai_investment_agent.domain.evaluation import CounterfactualOutcome, ModelHealthMetrics
from ai_investment_agent.evaluation.counterfactual import CounterfactualRecorder
from ai_investment_agent.evaluation.health import ModelHealthAssessor
from ai_investment_agent.evaluation.lifecycle import ModelPromotionService, PROMOTION_PATH
from ai_investment_agent.evaluation.quality import QualityEvaluator
from ai_investment_agent.health.checks import health
from ai_investment_agent.replay.service import ReplayService
from tests.horizon_support import bullish_long, judge, weak_short
from tests.support import make_agent, provided_capital

AS_OF = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


def test_journal_stores_every_action_including_no_trade():
    actions = {
        DecisionType.LONG_TERM_BUY: Action.BUY,
        DecisionType.HOLD: Action.HOLD,
        DecisionType.SELL: Action.SELL,
        DecisionType.NO_TRADE: Action.NO_TRADE,
        DecisionType.TACTICAL_WAIT: Action.TACTICAL_WAIT,
        DecisionType.EXIT_REVIEW: Action.EXIT_REVIEW,
    }
    stored: list[Action] = []
    for desired, expected_action in actions.items():
        agent, repository, _ = make_agent("known_market.json", desired=desired)
        snapshot = agent.judge(
            JudgmentRequest(ticker="005930", capital_context=provided_capital())
        )
        assert repository.get_snapshot(snapshot.decision_id) is not None
        record = snapshot.to_record()
        assert record.action is expected_action
        assert record.ticker == "005930"
        assert record.decision_id == snapshot.decision_id
        stored.append(record.action)
    assert Action.NO_TRADE in stored
    assert Action.TACTICAL_WAIT in stored
    assert Action.HOLD in stored
    assert Action.SELL in stored
    assert Action.EXIT_REVIEW in stored
    assert Action.BUY in stored


def test_decision_record_has_required_journal_fields():
    agent, _, _ = make_agent("known_market.json")
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )
    record = snapshot.to_record()
    dumped = record.model_dump(by_alias=True)
    for key in (
        "decisionId",
        "timestamp",
        "ticker",
        "marketSnapshot",
        "eventSnapshot",
        "featureSnapshot",
        "marketRegime",
        "longAnalysis",
        "shortAnalysis",
        "selectedHorizon",
        "action",
        "rawConfidence",
        "calibratedConfidence",
        "expectedReturn",
        "estimatedRisk",
        "suggestedCapitalPct",
        "reasonCodes",
        "thesis",
        "invalidationConditions",
        "modelVersion",
        "promptVersion",
        "featureVersion",
        "policyVersion",
    ):
        assert key in dumped
    assert record.confidence_is_probability is False
    assert record.raw_confidence == snapshot.proposal.raw_confidence
    assert record.calibrated_confidence is None
    assert record.event_snapshot == snapshot.events
    assert snapshot.counterfactual.source == "unmeasured"


def test_long_short_journal_captures_horizon_analyses():
    snapshot = judge(long_features=bullish_long(), short_features=weak_short())
    record = snapshot.to_record()
    assert record.long_analysis is not None
    assert record.short_analysis is not None
    assert record.selected_horizon is not None
    assert record.action in {Action.BUY, Action.NO_TRADE, Action.TACTICAL_WAIT}


def test_missing_calibration_does_not_invent_calibrated_confidence():
    agent, _, _ = make_agent("known_market.json")
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )
    assert snapshot.proposal.raw_confidence == pytest.approx(0.72)
    assert snapshot.proposal.calibrated_confidence is None
    assert snapshot.to_record().confidence.calibration_applied is False
    assert snapshot.to_record().confidence.treated_as_probability is False


def test_offline_calibration_table_sets_calibrated_confidence():
    table = CalibrationTable(pairs=((0.0, 0.2), (1.0, 0.8)))
    agent, _, _ = make_agent("known_market.json", calibration=table)
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )
    calibrated = snapshot.proposal.calibrated_confidence
    assert calibrated is not None
    assert 0.2 < calibrated < 0.8
    assert calibrated != snapshot.proposal.raw_confidence
    empty = CalibrationTable(pairs=())
    assert empty.apply(0.72) is None


def test_replay_restores_snapshot_inputs_and_versions():
    agent, repository, _ = make_agent("known_market.json")
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )
    bundle = ReplayService(repository).replay(snapshot.decision_id)
    assert bundle.decision_id == snapshot.decision_id
    assert bundle.market_snapshot == snapshot.market_snapshot
    assert bundle.event_snapshot == snapshot.events
    assert bundle.market_regime == snapshot.market_regime
    assert bundle.proposal.action == snapshot.proposal.action
    assert bundle.versions.model_version == snapshot.proposal.model_version
    assert bundle.versions.prompt_version == snapshot.prompt_version
    assert bundle.versions.feature_version == snapshot.proposal.feature_version
    assert bundle.versions.policy_version == snapshot.proposal.policy_version
    assert bundle.deterministic_rerun is False
    assert bundle.journal
    with pytest.raises(DecisionNotFoundError):
        ReplayService(repository).replay("dec_" + "0" * 32)


def test_counterfactual_can_be_recorded_without_an_order():
    agent, repository, _ = make_agent("known_market.json")
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )
    outcome = CounterfactualOutcome(
        return_1h=Decimal("0.002"),
        return_1d=Decimal("0.01"),
        return_5d=Decimal("0.03"),
        return_20d=Decimal("0.04"),
        mfe=Decimal("0.05"),
        mae=Decimal("0.02"),
        measured_at=AS_OF,
        source="fixture_price_path",
    )
    updated = CounterfactualRecorder(repository).record(snapshot.decision_id, outcome)
    assert updated.counterfactual.is_measured is True
    assert updated.counterfactual.return_1d == Decimal("0.01")
    assert updated.counterfactual.mfe == Decimal("0.05")
    replayed = ReplayService(repository).replay(snapshot.decision_id)
    assert replayed.counterfactual.return_20d == Decimal("0.04")


def test_unknown_model_health_is_not_healthy():
    unknown = ModelHealthAssessor().assess([])
    assert unknown.status is ModelHealthStatus.UNKNOWN
    assert unknown.treated_as_healthy is False
    payload = health(unknown)
    assert payload["modelHealth"] == "UNKNOWN"
    assert payload["modelHealthTreatedAsHealthy"] is False
    assert payload["unknownIsHealthy"] is False
    assert ModelHealthMetrics.unknown().status is not ModelHealthStatus.HEALTHY

    agent, repository, _ = make_agent("known_market.json")
    snapshot = agent.judge(
        JudgmentRequest(ticker="005930", capital_context=provided_capital())
    )
    logged_only = ModelHealthAssessor().assess(repository.list_snapshots())
    assert logged_only.sample_size == 1
    assert logged_only.outcome_sample_size == 0
    assert logged_only.status is ModelHealthStatus.UNKNOWN
    assert snapshot.proposal.action is Action.BUY


def test_quality_axes_are_separated_and_exclude_execution():
    report = QualityEvaluator().evaluate([])
    axes = {score.axis for score in report.axes}
    assert axes == {
        QualityAxis.ALPHA_QUALITY,
        QualityAxis.HORIZON_SELECTION_QUALITY,
        QualityAxis.RISK_ASSESSMENT_QUALITY,
        QualityAxis.CAPITAL_ALLOCATION_QUALITY,
    }
    assert all(score.status is EvaluationStatus.INSUFFICIENT_SAMPLE for score in report.axes)
    assert not hasattr(report, "execution")
    dumped = report.model_dump()
    assert "execution" not in dumped
    assert "executionQuality" not in dumped


def test_online_self_learning_is_forbidden():
    service = ModelPromotionService()
    assert service.current() is ModelLifecycleStage.DECISION_LOGS
    assert PROMOTION_PATH == (
        ModelLifecycleStage.DECISION_LOGS,
        ModelLifecycleStage.OFFLINE_EVALUATION,
        ModelLifecycleStage.CANDIDATE_MODEL,
        ModelLifecycleStage.BACKTEST,
        ModelLifecycleStage.SHADOW,
        ModelLifecycleStage.APPROVED,
        ModelLifecycleStage.NEW_VERSION,
    )
    with pytest.raises(OnlineLearningForbiddenError):
        service.apply_online_update(loss=Decimal("-0.08"))
    service.advance(ModelLifecycleStage.OFFLINE_EVALUATION)
    with pytest.raises(ValueError):
        service.advance(ModelLifecycleStage.APPROVED)
