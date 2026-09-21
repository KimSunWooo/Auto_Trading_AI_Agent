from ai_investment_agent.adapters.event_store import EventStoreDeleteError
from ai_investment_agent.domain.enums import IntelligenceKind, VerificationStatus
from tests.event_support import make_engine, raw_event
import pytest


def test_correction_marks_event_retracted_without_deleting():
    engine, store = make_engine()
    original = engine.ingest(
        raw_event(
            raw_id="raw_rate_1",
            source="reuters",
            headline="Fed holds rates at 5.25 percent",
            body="The Federal Reserve holds interest rates unchanged.",
        )
    )
    event_id = original.event_id
    cluster_id = original.cluster_id

    retracted = engine.retract(
        event_id,
        raw_event(
            raw_id="raw_rate_correction",
            source="reuters",
            headline="정정보도: 연준 금리 동결 기사는 오보입니다",
            body="We retract the earlier report. 앞서 보도한 금리 동결 기사는 오보 정정입니다.",
            kind=IntelligenceKind.FOREIGN_NEWS,
        ),
    )

    assert retracted.event_id == event_id
    assert retracted.cluster_id == cluster_id
    assert retracted.verification_status is VerificationStatus.RETRACTED
    assert store.get(event_id) is not None
    assert store.get(event_id).verification_status is VerificationStatus.RETRACTED
    assert retracted.article_count == 2
    with pytest.raises(EventStoreDeleteError):
        store.delete(event_id)
    assert len(store) == 1
