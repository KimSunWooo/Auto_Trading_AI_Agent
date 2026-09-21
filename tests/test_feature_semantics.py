from datetime import timedelta
from decimal import Decimal

from ai_investment_agent.analysis.features import long_features_from
from ai_investment_agent.analysis.service import analyzed_to_market_event
from ai_investment_agent.domain.enums import (
    Action,
    EventCategory,
    EventDirection,
    Horizon,
    ImpactHorizon,
    MarketRegimeType,
    ReasonCode,
)
from ai_investment_agent.domain.market import MarketRegime
from ai_investment_agent.features.event_features import EventFeatureCalculator
from ai_investment_agent.features.mathutil import moving_average, to_decimal
from ai_investment_agent.features.quantitative import QuantitativeFeatureCalculator
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig
from tests.context_support import AS_OF, analyzed_event, engine, rising_series
from tests.horizon_support import (
    bullish_long,
    bullish_short,
    good_entry,
    judge,
    make_regime,
    weak_long,
    weak_short,
)


def test_ma_names_match_configured_windows():
    cfg = FeaturePolicyConfig()
    assert cfg.ma20_window == 20
    assert cfg.ma60_window == 60
    assert cfg.ma120_window == 120
    series = rising_series(n=130)
    quant = QuantitativeFeatureCalculator(cfg).compute(series, as_of=AS_OF)
    closes = [float(price) for price in series.closes]
    assert quant.ma20 == to_decimal(moving_average(closes, 20))
    assert quant.ma60 == to_decimal(moving_average(closes, 60))
    assert quant.ma120 == to_decimal(moving_average(closes, 120))
    assert quant.ma20 != quant.ma60
    assert quant.ma60 != quant.ma120
    features = long_features_from(engine().build(ticker="005930", as_of=AS_OF, series=series))
    assert features.ma20 == quant.ma20
    assert features.ma60 == quant.ma60
    assert features.ma120 == quant.ma120


def test_weekly_trend_is_not_copied_from_daily():
    series = rising_series(n=40)
    context = engine().build(ticker="005930", as_of=AS_OF, series=series)
    assert context.quantitative.trend is not None
    assert context.quantitative.weekly_trend is None
    features = long_features_from(context)
    assert features.daily_trend == context.quantitative.trend
    assert features.weekly_trend is None
    assert features.weekly_trend != features.daily_trend


def test_no_sector_event_does_not_invent_sector_strength():
    context = engine().build(ticker="005930", as_of=AS_OF, series=rising_series())
    assert context.event_features.sector_risk == 0.0
    features = long_features_from(context)
    assert features.sector_strength is None
    assert features.sector_strength != Decimal("1")


def test_old_published_event_analyzed_late_is_not_fresh():
    published = AS_OF - timedelta(days=4)
    event = analyzed_event(
        category=EventCategory.CORPORATE,
        direction=EventDirection.POSITIVE,
        magnitude=0.8,
        source_trust=1.0,
        novelty=1.0,
        confidence=0.9,
        horizon=ImpactHorizon.DAYS,
        published_at=published,
        analyzed_at=AS_OF,
    )
    assert event.analyzed_at != event.market_available_at
    assert event.market_available_at == published
    calc = EventFeatureCalculator()
    decay = calc.time_decay_for(event, AS_OF)
    fresh = analyzed_event(
        published_at=AS_OF,
        analyzed_at=AS_OF,
        magnitude=0.8,
        source_trust=1.0,
        novelty=1.0,
        confidence=0.9,
        horizon=ImpactHorizon.DAYS,
    )
    assert decay < calc.time_decay_for(fresh, AS_OF)
    assert decay == 0.5 ** (4 / 2)


def test_missing_market_available_at_is_not_treated_as_fresh():
    event = analyzed_event(analyzed_at=AS_OF, published_at=AS_OF)
    event = event.model_copy(update={"market_available_at": None, "published_at": None})
    assert EventFeatureCalculator().time_decay_for(event, AS_OF) == 0.0


def test_future_market_available_at_is_look_ahead_zero_decay():
    event = analyzed_event(
        published_at=AS_OF + timedelta(days=1),
        analyzed_at=AS_OF + timedelta(days=1),
    )
    assert EventFeatureCalculator().time_decay_for(event, AS_OF) == 0.0


def test_analyzed_to_market_event_does_not_use_analyzed_at_as_occurred():
    event = analyzed_event(
        published_at=AS_OF - timedelta(hours=3),
        analyzed_at=AS_OF,
    )
    mapped = analyzed_to_market_event(event, "005930")
    assert mapped.occurred_at != event.analyzed_at
    assert mapped.occurred_at == event.market_available_at
    assert mapped.payload["analyzedAt"] == event.analyzed_at.isoformat()


def test_long_selection_uses_long_agent_metrics():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
    )
    assert snapshot.proposal.action is Action.BUY
    assert snapshot.proposal.horizon is Horizon.LONG_TERM
    assert ReasonCode.METRICS_FROM_LONG_AGENT.value in snapshot.proposal.reason_codes
    assert snapshot.proposal.expected_return == snapshot.long_analysis.utility.expected_return
    long_risk = (
        snapshot.long_analysis.utility.risk_penalty
        + snapshot.long_analysis.utility.tail_risk
        + snapshot.long_analysis.utility.drawdown_penalty
    )
    assert snapshot.proposal.estimated_risk == long_risk
    assert snapshot.proposal.expected_return != Decimal("0.06")


def test_short_selection_uses_short_agent_metrics():
    snapshot = judge(
        long_features=weak_long(),
        short_features=bullish_short(),
        entry=good_entry(),
    )
    assert snapshot.proposal.action is Action.BUY
    assert snapshot.proposal.horizon is Horizon.SHORT_TERM
    assert ReasonCode.METRICS_FROM_SHORT_AGENT.value in snapshot.proposal.reason_codes
    assert snapshot.proposal.expected_return == snapshot.short_analysis.utility.expected_return
    short_risk = (
        snapshot.short_analysis.utility.risk_penalty
        + snapshot.short_analysis.utility.tail_risk
        + snapshot.short_analysis.utility.drawdown_penalty
    )
    assert snapshot.proposal.estimated_risk == short_risk
    assert snapshot.proposal.expected_return != Decimal("0.02")


def test_selected_long_confidence_is_not_min_with_weak_short():
    snapshot = judge(
        long_features=bullish_long(),
        short_features=weak_short(),
        entry=good_entry(),
    )
    long_conf = snapshot.long_analysis.confidence
    short_conf = snapshot.short_analysis.confidence
    assert short_conf < long_conf
    raw = snapshot.proposal.raw_confidence
    assert raw > min(long_conf, short_conf)
    assessment = snapshot.confidence_assessment
    assert assessment is not None
    assert assessment.selected_agent_confidence == long_conf
    assert assessment.treated_as_probability is False
    assert assessment.calibrated_confidence is None
    assert "selectedAgent=long" in assessment.provenance


def test_crisis_and_event_risk_are_known_but_not_safe():
    crisis = make_regime(MarketRegimeType.CRISIS)
    event_risk = make_regime(MarketRegimeType.EVENT_RISK)
    unknown = make_regime(MarketRegimeType.UNKNOWN)
    assert crisis.is_known is True
    assert event_risk.is_known is True
    assert crisis.treated_as_safe is False
    assert event_risk.treated_as_safe is False
    assert unknown.treated_as_safe is False
    sideways = MarketRegime(
        regime=MarketRegimeType.SIDEWAYS,
        confidence=0.6,
        as_of=AS_OF,
        explanation="fixture",
    )
    assert sideways.treated_as_safe is True
