from ai_investment_agent.domain.enums import ContextSignal, EventCategory, EventDirection
from tests.context_support import AS_OF, analyzed_event, engine, rising_series


def test_positive_news_negative_market_creates_divergence():
    event = analyzed_event(
        category=EventCategory.CORPORATE,
        direction=EventDirection.POSITIVE,
        magnitude=0.8,
        source_trust=0.9,
        novelty=0.9,
        confidence=0.9,
        headline="Earnings beat",
    )
    calc = engine()
    aligned = calc.build(
        ticker="005930",
        as_of=AS_OF,
        series=rising_series(),
        events=[event],
        post_event_reaction=0.03,
        market_reaction=0.03,
    )
    diverged = calc.build(
        ticker="005930",
        as_of=AS_OF,
        series=rising_series(),
        events=[event],
        post_event_reaction=-0.04,
        market_reaction=-0.04,
    )

    assert diverged.divergences
    signal = diverged.divergences[0]
    assert signal.code is ContextSignal.EVENT_MARKET_DIVERGENCE
    assert signal.event_direction is EventDirection.POSITIVE
    assert signal.market_reaction < 0
    assert signal.confidence_adjustment < 0
    assert aligned.event_features.event_confidence > diverged.event_features.event_confidence
    assert not any(item.code is ContextSignal.EVENT_MARKET_DIVERGENCE for item in aligned.divergences)
