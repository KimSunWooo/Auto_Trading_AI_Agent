from ai_investment_agent.domain.enums import EventCategory, EventDirection
from tests.context_support import AS_OF, analyzed_event, engine, rising_series


def test_high_priced_in_means_low_remaining_edge():
    event = analyzed_event(
        category=EventCategory.CORPORATE,
        direction=EventDirection.POSITIVE,
        magnitude=0.9,
        source_trust=1.0,
        novelty=1.0,
        confidence=1.0,
    )
    context = engine().build(
        ticker="005930",
        as_of=AS_OF,
        series=rising_series(),
        events=[event],
        post_event_reaction=0.7,
        volume_reaction=0.8,
        prior_price_movement=0.02,
        market_reaction=0.65,
        sector_reaction=0.5,
    )

    priced = context.priced_in
    assert priced is not None
    assert priced.already_priced_in is not None
    assert priced.remaining_edge is not None
    assert priced.already_priced_in > 0.6
    assert priced.remaining_edge < priced.already_priced_in
    assert priced.remaining_edge < 0.4
    assert priced.post_event_reaction == 0.7
    assert priced.method == "heuristic_v1"
