from datetime import timedelta

from ai_investment_agent.domain.enums import EventCategory, EventDirection, ImpactHorizon
from tests.context_support import AS_OF, analyzed_event, engine, rising_series


def test_event_impact_decays_with_time():
    event = analyzed_event(
        category=EventCategory.CORPORATE,
        direction=EventDirection.POSITIVE,
        magnitude=0.8,
        source_trust=1.0,
        novelty=1.0,
        confidence=0.9,
        horizon=ImpactHorizon.DAYS,
        analyzed_at=AS_OF,
    )
    calc = engine()
    now = calc.build(ticker="005930", as_of=AS_OF, series=rising_series(), events=[event])
    later = calc.build(
        ticker="005930",
        as_of=AS_OF + timedelta(days=4),
        series=rising_series(),
        events=[event],
    )

    assert now.event_features.time_decay > later.event_features.time_decay
    assert now.event_features.effective_impact > later.event_features.effective_impact
    assert later.event_features.time_decay == 0.5 ** (4 / 2)
