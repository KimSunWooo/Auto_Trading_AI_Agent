from datetime import datetime, timezone

from ai_investment_agent.collectors.intelligence import FixtureNewsCollector
from ai_investment_agent.collectors.market import FixtureMarketDataCollector
from ai_investment_agent.domain.enums import CollectionStatus, IntelligenceKind, MarketDataKind
from ai_investment_agent.replay.as_of import AsOfView, accessible_as_of
from tests.collection_support import FIXED_AS_OF


def test_future_market_data_excluded_from_past_snapshot():
    collector = FixtureMarketDataCollector.from_file()
    past = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    result = collector.collect("005930", past, kinds=[MarketDataKind.CURRENT_PRICE])

    ids = {item.record_id for item in result.items}
    assert "md_price_005930_past" in ids
    assert "md_price_005930_current" not in ids
    assert "md_price_005930_future" not in ids


def test_future_price_not_in_current_as_of_window():
    collector = FixtureMarketDataCollector.from_file()
    result = collector.collect("005930", FIXED_AS_OF, kinds=[MarketDataKind.CURRENT_PRICE])
    ids = {item.record_id for item in result.items}
    assert "md_price_005930_current" in ids
    assert "md_price_005930_past" in ids
    assert "md_price_005930_future" not in ids


def test_unpublished_past_event_is_not_used_before_tradable_at():
    collector = FixtureNewsCollector.from_file()
    result = collector.collect("005930", FIXED_AS_OF)

    assert result.status is CollectionStatus.OK
    ids = {item.record_id for item in result.items}
    assert "int_news_domestic_005930" in ids
    assert "int_news_foreign_005930" in ids
    assert "int_news_lookahead_trap" not in ids
    for item in result.items:
        assert item.timestamps.tradable_at <= FIXED_AS_OF
        assert item.timestamps.source_received_at is not None
        assert item.timestamps.source_received_at <= FIXED_AS_OF


def test_lookahead_trap_becomes_visible_only_after_publish():
    collector = FixtureNewsCollector.from_file()
    after_publish = datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc)
    result = collector.collect("005930", after_publish)
    ids = {item.record_id for item in result.items}
    assert "int_news_lookahead_trap" in ids


def test_replay_as_of_view_filters_both_domains_independently():
    market = FixtureMarketDataCollector.from_file()
    news = FixtureNewsCollector.from_file()
    view = AsOfView(FIXED_AS_OF)

    market_now = market.collect("005930", datetime(2026, 12, 1, tzinfo=timezone.utc))
    news_now = news.collect("005930", datetime(2026, 12, 1, tzinfo=timezone.utc))

    market_as_of = view.take(market_now.items)
    news_as_of = view.take(news_now.items)

    assert market_as_of
    assert news_as_of
    assert all(item.kind in MarketDataKind for item in market_as_of)
    assert all(item.kind in IntelligenceKind for item in news_as_of)
    assert {item.record_id for item in market_as_of} == {
        item.record_id
        for item in accessible_as_of(market_now.items, FIXED_AS_OF)
    }
    assert "md_price_005930_future" not in {item.record_id for item in market_as_of}
    assert "int_news_lookahead_trap" not in {item.record_id for item in news_as_of}
