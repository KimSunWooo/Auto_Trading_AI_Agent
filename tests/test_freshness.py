from datetime import timedelta

from ai_investment_agent.collectors.market import FixtureMarketDataCollector
from ai_investment_agent.domain.collection import FRESHNESS_MAX_AGE, is_stale
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass, MarketDataKind
from ai_investment_agent.domain.market_feed import MarketDataRecord
from tests.collection_support import FIXED_AS_OF, make_timestamps


def test_same_age_is_stale_for_ultra_fast_but_fresh_for_intraday():
    available_at = FIXED_AS_OF - timedelta(hours=1)
    timestamps = make_timestamps(available_at)
    assert is_stale(timestamps, FIXED_AS_OF, FreshnessClass.ULTRA_FAST) is True
    assert is_stale(timestamps, FIXED_AS_OF, FreshnessClass.INTRADAY) is False
    assert FRESHNESS_MAX_AGE[FreshnessClass.ULTRA_FAST] < timedelta(hours=1)
    assert FRESHNESS_MAX_AGE[FreshnessClass.INTRADAY] > timedelta(hours=1)


def test_same_age_is_stale_for_daily_but_fresh_for_long_horizon():
    available_at = FIXED_AS_OF - timedelta(days=2)
    timestamps = make_timestamps(available_at)
    assert is_stale(timestamps, FIXED_AS_OF, FreshnessClass.DAILY) is True
    assert is_stale(timestamps, FIXED_AS_OF, FreshnessClass.LONG_HORIZON) is False


def test_collector_marks_stale_ultra_fast_quote():
    available_at = FIXED_AS_OF - timedelta(hours=1)
    record = MarketDataRecord(
        record_id="old_px",
        kind=MarketDataKind.CURRENT_PRICE,
        instrument="005930",
        timestamps=make_timestamps(available_at),
        freshness_class=FreshnessClass.ULTRA_FAST,
        value="70000",
        currency="KRW",
    )
    result = FixtureMarketDataCollector([record]).collect("005930", FIXED_AS_OF)
    assert result.status is CollectionStatus.STALE
    assert result.stale_item_ids == ["old_px"]
    assert result.items[0].record_id == "old_px"


def test_intraday_quote_of_same_age_is_ok():
    available_at = FIXED_AS_OF - timedelta(hours=1)
    record = MarketDataRecord(
        record_id="fx1",
        kind=MarketDataKind.FX,
        instrument="USDKRW",
        timestamps=make_timestamps(available_at),
        freshness_class=FreshnessClass.INTRADAY,
        value="1340",
    )
    result = FixtureMarketDataCollector([record]).collect("USDKRW", FIXED_AS_OF)
    assert result.status is CollectionStatus.OK
    assert result.stale_item_ids == []


def test_future_data_is_lookahead_not_stale():
    future = make_timestamps(FIXED_AS_OF + timedelta(hours=1))
    assert is_stale(future, FIXED_AS_OF, FreshnessClass.ULTRA_FAST) is False
