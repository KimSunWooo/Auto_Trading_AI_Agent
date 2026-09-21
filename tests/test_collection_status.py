from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ai_investment_agent.collectors.intelligence import FixtureNewsCollector
from ai_investment_agent.collectors.market import FixtureMarketDataCollector
from ai_investment_agent.domain.collection import CollectionResult, CollectionTimestamps
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass, IntelligenceKind, MarketDataKind
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord
from ai_investment_agent.domain.market_feed import MarketDataRecord
from tests.collection_support import FIXED_AS_OF, make_timestamps


def test_api_failure_is_data_unavailable_not_no_event():
    collector = FixtureNewsCollector(records=[], unavailable=True)
    result = collector.collect("005930", FIXED_AS_OF)

    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT
    assert result.failed is True
    assert result.is_no_event is False
    assert result.items == []
    assert result.error
    assert "API failure" in result.error


def test_successful_empty_news_feed_is_no_event():
    collector = FixtureNewsCollector(records=[])
    result = collector.collect("005930", FIXED_AS_OF)

    assert result.status is CollectionStatus.NO_EVENT
    assert result.status is not CollectionStatus.DATA_UNAVAILABLE
    assert result.failed is False
    assert result.is_no_event is True
    assert result.items == []
    assert result.error is None


def test_data_unavailable_and_no_event_are_not_interchangeable():
    failed = FixtureNewsCollector(unavailable=True).collect(None, FIXED_AS_OF)
    quiet = FixtureNewsCollector([]).collect(None, FIXED_AS_OF)
    assert failed.status != quiet.status
    assert failed.items == quiet.items == []
    assert (failed.status, failed.error) != (quiet.status, quiet.error)


def test_missing_market_quote_is_unavailable_not_no_event():
    collector = FixtureMarketDataCollector(records=[])
    result = collector.collect("NO_SUCH", FIXED_AS_OF)

    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT
    assert result.items == []
    assert result.error


def test_ok_cannot_be_an_empty_list():
    with pytest.raises(ValidationError):
        CollectionResult.ok([], as_of=FIXED_AS_OF)


def test_no_event_cannot_carry_an_error():
    with pytest.raises(ValidationError):
        CollectionResult(
            status=CollectionStatus.NO_EVENT,
            items=[],
            error="timeout",
            as_of=FIXED_AS_OF,
        )


def test_data_unavailable_cannot_look_like_success_with_items():
    timestamps = make_timestamps(FIXED_AS_OF)
    item = IntelligenceRecord(
        record_id="n1",
        kind=IntelligenceKind.DOMESTIC_NEWS,
        headline="should not be returned on failure",
        timestamps=timestamps,
        freshness_class=FreshnessClass.INTRADAY,
    )
    with pytest.raises(ValidationError):
        CollectionResult(
            status=CollectionStatus.DATA_UNAVAILABLE,
            items=[item],
            error="timeout",
            as_of=FIXED_AS_OF,
        )


def test_failed_market_api_does_not_return_cached_empty_success():
    timestamps = make_timestamps(datetime(2026, 9, 21, 8, 59, tzinfo=timezone.utc))
    record = MarketDataRecord(
        record_id="px",
        kind=MarketDataKind.CURRENT_PRICE,
        instrument="005930",
        timestamps=timestamps,
        freshness_class=FreshnessClass.ULTRA_FAST,
        value="71000",
        currency="KRW",
    )
    collector = FixtureMarketDataCollector([record], unavailable=True)
    result = collector.collect("005930", FIXED_AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.items == []


def test_news_and_market_collectors_do_not_mix_domains():
    from ai_investment_agent.collectors.intelligence import FixtureDisclosureCollector

    news = FixtureNewsCollector.from_file().collect("005930", FIXED_AS_OF)
    assert news.status is CollectionStatus.OK
    assert {item.kind for item in news.items} <= {
        IntelligenceKind.DOMESTIC_NEWS,
        IntelligenceKind.FOREIGN_NEWS,
    }

    disclosure = FixtureDisclosureCollector.from_file().collect("005930", FIXED_AS_OF)
    assert {item.kind for item in disclosure.items} == {IntelligenceKind.CORPORATE_DISCLOSURE}

    market = FixtureMarketDataCollector.from_file().collect("005930", FIXED_AS_OF)
    assert market.items
    assert {item.kind for item in market.items} <= set(MarketDataKind)


def test_collection_timestamps_include_all_integrity_fields():
    ts = CollectionTimestamps(
        event_occurred_at=datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc),
        published_at=datetime(2026, 9, 21, 8, 0, 1, tzinfo=timezone.utc),
        source_received_at=datetime(2026, 9, 21, 8, 0, 2, tzinfo=timezone.utc),
        collected_at=datetime(2026, 9, 21, 8, 0, 3, tzinfo=timezone.utc),
        normalized_at=datetime(2026, 9, 21, 8, 0, 4, tzinfo=timezone.utc),
        analyzed_at=datetime(2026, 9, 21, 8, 0, 5, tzinfo=timezone.utc),
        tradable_at=datetime(2026, 9, 21, 8, 0, 2, tzinfo=timezone.utc),
    )
    dumped = ts.model_dump(by_alias=True)
    for key in (
        "eventOccurredAt",
        "publishedAt",
        "sourceReceivedAt",
        "collectedAt",
        "normalizedAt",
        "analyzedAt",
        "tradableAt",
    ):
        assert key in dumped
        assert dumped[key] is not None
