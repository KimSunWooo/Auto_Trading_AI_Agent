from ai_investment_agent.domain.enums import EventCategory, EventDirection, MarketRegimeType
from tests.context_support import AS_OF, analyzed_event, engine, rising_series


def test_high_event_risk_sets_event_risk_regime():
    event = analyzed_event(
        category=EventCategory.GEOPOLITICAL,
        direction=EventDirection.NEGATIVE,
        magnitude=0.95,
        source_trust=1.0,
        novelty=1.0,
        confidence=0.95,
        headline="Missile strike raises geopolitical risk",
    )
    context = engine().build(
        ticker="005930",
        as_of=AS_OF,
        series=rising_series(),
        events=[event],
        liquidity=0.8,
    )

    assert context.event_features.effective_impact >= 0.45
    assert context.event_features.geopolitical_risk >= 0.45
    assert context.regime.regime is MarketRegimeType.EVENT_RISK
    assert context.regime.is_known is True
    assert context.regime.treated_as_safe is False
    assert context.regime.regime is not MarketRegimeType.UNKNOWN
    assert context.event_features.dominant_category is EventCategory.GEOPOLITICAL
