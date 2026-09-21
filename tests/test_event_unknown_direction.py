from ai_investment_agent.domain.enums import EventDirection
from tests.event_support import make_engine, raw_event


def test_unknown_event_is_not_forced_positive_or_negative():
    engine, _ = make_engine()
    event = engine.ingest(
        raw_event(
            raw_id="raw_board",
            source="yonhap",
            headline="Samsung Electronics held a board meeting",
            body="삼성전자가 정기 이사회를 열고 일상적인 지배구조 안건을 논의했다. No guidance was issued.",
            ticker="005930",
            country="KR",
        )
    )

    assert event.direction is EventDirection.UNKNOWN
    assert event.direction not in {EventDirection.POSITIVE, EventDirection.NEGATIVE}
    assert event.event_type in {"BOARD_MEETING", "UNKNOWN"}
    assert event.confidence <= 0.85
