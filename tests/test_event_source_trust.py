from datetime import timedelta

from ai_investment_agent.domain.enums import SourceTier
from ai_investment_agent.policy.source_trust import source_tier_for, source_trust_score
from tests.event_support import FIXED_NOW, make_engine, raw_event


def test_low_trust_source_lowers_source_trust():
    engine, _ = make_engine()
    official = engine.ingest(
        raw_event(
            raw_id="raw_dart",
            source="dart.fss.or.kr",
            headline="삼성전자 정기공시",
            body="삼성전자가 이사회 개최 사실을 공시했다.",
            ticker="005930",
            published_at=FIXED_NOW,
        )
    )
    rumored = engine.ingest(
        raw_event(
            raw_id="raw_sns",
            source="dcinside.com/community",
            headline="익명 게시판 급등 루머",
            body="커뮤니티 사용자가 급등을 주장했다.",
            published_at=FIXED_NOW - timedelta(days=5),
        )
    )

    assert source_tier_for("dart.fss.or.kr") is SourceTier.S
    assert source_tier_for("twitter.com/unknown") is SourceTier.D
    assert official.source_tier is SourceTier.S
    assert rumored.source_tier is SourceTier.D
    assert rumored.source_trust < official.source_trust
    assert rumored.source_trust == source_trust_score("dcinside.com/community")
    assert rumored.source_trust <= 0.2
    assert official.source_trust == 1.0
    assert rumored.verification_status.value in {"UNVERIFIED", "PARTIALLY_VERIFIED"}
