"""10.5.8 Market/news/macro quality: timestamps, volume, stable ids, empty vs corrupt."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_investment_agent.adapters.live.macro.parser import parse_macro_payload
from ai_investment_agent.adapters.live.market.parser import parse_market_payload
from ai_investment_agent.adapters.live.news import LiveNewsCollector
from ai_investment_agent.adapters.live.news.parser import parse_news_payload, stable_news_record_id
from ai_investment_agent.domain.enums import CollectionStatus, MarketDataKind
from tests.test_live_news import _client, FakeTransport
import json


AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def test_timestamp_less_market_scalar_is_not_fresh_data():
    records = parse_market_payload(
        {"instrument": "005930", "currentPrice": "71000"},
        instrument="005930",
        collected_at=AS_OF,
    )
    assert records == []


def test_market_dict_without_timestamps_is_skipped():
    records = parse_market_payload(
        {"instrument": "005930", "currentPrice": {"value": "71000"}},
        instrument="005930",
        collected_at=AS_OF,
    )
    assert records == []


def test_invalid_numeric_values_are_skipped():
    records = parse_market_payload(
        {
            "instrument": "005930",
            "currentPrice": {
                "value": "N/A",
                "eventOccurredAt": "2026-09-21T08:59:30+00:00",
                "sourceReceivedAt": "2026-09-21T08:59:31+00:00",
                "tradableAt": "2026-09-21T08:59:31+00:00",
            },
        },
        instrument="005930",
        collected_at=AS_OF,
    )
    assert records == []


def test_ohlcv_missing_volume_is_not_zero():
    records = parse_market_payload(
        {
            "instrument": "005930",
            "dailyBars": [
                {
                    "open": "1",
                    "high": "2",
                    "low": "0.5",
                    "close": "1.5",
                    "barStart": "2026-09-20T00:00:00+00:00",
                    "barEnd": "2026-09-20T06:00:00+00:00",
                }
            ],
        },
        instrument="005930",
        collected_at=AS_OF,
    )
    assert not any(item.kind is MarketDataKind.OHLCV for item in records)


def test_news_ids_are_process_stable():
    first = stable_news_record_id("https://wire.example/n1")
    second = stable_news_record_id("https://wire.example/n1")
    assert first == second
    assert first.startswith("news_")
    assert first != stable_news_record_id("https://wire.example/n2")


def test_news_correction_links_related_id():
    records = parse_news_payload(
        {
            "articles": [
                {
                    "id": "n1-corr",
                    "title": "Correction",
                    "body": "Updated",
                    "publishedAt": "2026-09-21T08:00:00+00:00",
                    "is_correction": True,
                    "relatedId": "n1",
                    "ticker": "005930",
                    "kind": "DOMESTIC_NEWS",
                }
            ]
        },
        ticker="005930",
        collected_at=AS_OF,
    )
    assert records[0].record_id == stable_news_record_id("n1-corr")
    assert "[CORRECTION]" in (records[0].body or "")
    assert "[RELATED:n1]" in (records[0].body or "")
    assert records[0].raw_ref == "n1"


def test_news_empty_list_is_no_event_via_collector():
    collector = LiveNewsCollector(
        client=_client(FakeTransport([(200, json.dumps({"articles": []}).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.NO_EVENT


def test_news_corrupt_items_are_unavailable():
    collector = LiveNewsCollector(
        client=_client(FakeTransport([(200, json.dumps({"articles": [{"id": "x"}]}).encode())])),
        received_at_fn=lambda: AS_OF,
    )
    result = collector.collect("005930", AS_OF)
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT
    assert collector.last_diagnostics is not None
    assert collector.last_diagnostics.error_code == "SCHEMA_INVALID"


def test_macro_corrupt_items_are_not_no_event():
    try:
        parse_macro_payload({"items": [{"id": "x"}]}, collected_at=AS_OF)
    except ValueError as exc:
        assert "required fields" in str(exc)
    else:
        raise AssertionError("corrupt macro payload must raise")


def test_news_missing_articles_key_is_corrupt():
    try:
        parse_news_payload({"ok": True}, ticker="005930", collected_at=AS_OF)
    except ValueError as exc:
        assert "missing articles" in str(exc)
    else:
        raise AssertionError("missing articles must raise")
