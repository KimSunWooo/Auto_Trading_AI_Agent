from ai_investment_agent.domain.enums import EventCategory, EventDirection, VerificationStatus
from tests.event_support import make_engine, raw_event


def test_duplicate_articles_collapse_to_one_event():
    engine, store = make_engine()
    reuters = raw_event(
        raw_id="raw_reuters_fed",
        source="reuters",
        headline="Fed holds rates at 5.25 percent citing sticky inflation",
        body="The Federal Reserve holds interest rates unchanged at 5.25 percent.",
        country="US",
    )
    yonhap = raw_event(
        raw_id="raw_yonhap_fed",
        source="yonhap",
        headline="Federal Reserve keeps interest rates unchanged at 5.25 percent",
        body="연준이 기준금리를 5.25 percent로 동결했다. Inflation remains sticky.",
        country="US",
    )

    events = engine.ingest_many([reuters, yonhap])

    assert len(events) == 1
    event = events[0]
    assert event.article_count == 2
    assert event.article_count != 1 or len(store.list_all()) == 1
    assert len(store.list_all()) == 1
    assert set(event.member_raw_ids) == {"raw_reuters_fed", "raw_yonhap_fed"}
    assert event.category is EventCategory.MACRO
    assert event.event_type == "RATE_DECISION"
    assert event.direction is not None
    assert "action" not in event.model_dump()
    assert event.verification_status is VerificationStatus.VERIFIED
