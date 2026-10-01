"""10.5.8 closeout: bidirectional live cutoff and concurrent evaluate isolation.

Does not rewrite tests/test_live_acceptance_1058.py. Uses public APIs and
barrier/event interleaving on the shared app service.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Mapping

from ai_investment_agent.adapters.live.dart import LiveDisclosureCollector
from ai_investment_agent.adapters.live.factory import build_live_observation_service
from ai_investment_agent.adapters.live.llm import LiveLlmProvider
from ai_investment_agent.adapters.live.macro import LiveMacroCollector
from ai_investment_agent.adapters.live.market import LiveMarketDataCollector
from ai_investment_agent.adapters.live.news import LiveNewsCollector
from ai_investment_agent.analysis.clock import FIXTURE_AS_OF
from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.api.app import create_app
from ai_investment_agent.domain.enums import (
    CollectionStatus,
    DataMode,
    DecisionReadinessStatus,
)
from ai_investment_agent.health.report import collect_health
from tests.test_live_acceptance_1058 import _dart_row
from tests.test_live_observation import FakeTransport, _client, _llm_payload, _market_payload

T0 = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
FUTURE = datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _news_article(
    *,
    title: str,
    published: datetime,
    source_received: datetime | None = None,
    tradable: datetime | None = None,
    event_occurred: datetime | None = None,
    source: str = "wire-a",
    article_id: str = "n1",
    ticker: str = "005930",
) -> dict:
    item = {
        "id": article_id,
        "title": title,
        "publishedAt": _iso(published),
        "source": source,
        "kind": "DOMESTIC_NEWS",
        "ticker": ticker,
    }
    if source_received is not None:
        item["sourceReceivedAt"] = _iso(source_received)
    if tradable is not None:
        item["tradableAt"] = _iso(tradable)
    if event_occurred is not None:
        item["eventOccurredAt"] = _iso(event_occurred)
    return item


def _quiet_news_payload() -> bytes:
    return json.dumps({"status": "NO_EVENT", "articles": []}).encode()


def _quiet_macro_payload() -> bytes:
    return json.dumps({"status": "NO_EVENT", "items": []}).encode()


def _dart_ok_payload() -> bytes:
    return json.dumps({"status": "000", "list": [_dart_row()]}).encode()


def _dart_empty_payload() -> bytes:
    return json.dumps({"status": "013", "list": []}).encode()


def _fail_transport() -> FakeTransport:
    return FakeTransport(
        {
            "/market/": (500, b'{"error":"fail"}'),
            "/news": (500, b'{"error":"fail"}'),
            "/macro": (500, b'{"error":"fail"}'),
            "/list.json": (500, b'{"error":"fail"}'),
            "/chat/completions": (500, b'{"error":"fail"}'),
        }
    )


def _live_env(monkeypatch) -> None:
    monkeypatch.setenv("DART_API_KEY", "dart-test-key-xxxxxxxx")
    monkeypatch.setenv("DART_CORP_CODE_005930", "00126380")
    monkeypatch.setenv("DART_CORP_CODE_000660", "00164779")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-xxxxxxxxxxxx")


def _pin_market_clock(monkeypatch, clock: dict) -> None:
    class _PinnedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock["now"]
            if tz is None:
                return current
            return current.astimezone(tz)

    monkeypatch.setattr(
        "ai_investment_agent.adapters.live.market.datetime",
        _PinnedDateTime,
    )


def test_in_cycle_receive_does_not_disable_accessibility_filter():
    """include_current_receive uses received_at, not an unbounded cutoff."""
    receive = T0 + timedelta(seconds=12)
    collector = LiveNewsCollector(
        client=_client(
            "news",
            "https://news.example",
            FakeTransport(
                {
                    "/news": (
                        200,
                        json.dumps(
                            {
                                "articles": [
                                    _news_article(
                                        title="Vendor future timestamps",
                                        published=T0 - timedelta(hours=2),
                                        source_received=FUTURE,
                                        tradable=FUTURE,
                                        event_occurred=FUTURE,
                                    )
                                ]
                            }
                        ).encode(),
                    )
                }
            ),
        ),
        received_at_fn=lambda: receive,
    )
    result = collector.collect("005930", T0, include_current_receive=True)
    assert result.items == []
    assert result.status is CollectionStatus.NO_EVENT


def test_vendor_future_source_and_tradable_cannot_bypass_cutoff():
    receive = T0 + timedelta(seconds=8)
    payload = _market_payload()
    payload["currentPrice"] = {
        "value": "99999",
        "eventOccurredAt": _iso(T0 - timedelta(minutes=1)),
        "sourceReceivedAt": _iso(FUTURE),
        "tradableAt": _iso(FUTURE),
    }
    collector = LiveMarketDataCollector(
        client=_client(
            "market",
            "https://md.example",
            FakeTransport({"/market/": (200, json.dumps(payload).encode())}),
        )
    )
    result = collector.collect("005930", receive, include_current_receive=True)
    prices = [item for item in result.items if item.kind.value == "CURRENT_PRICE"]
    assert prices == []


def test_vendor_future_event_occurred_at_does_not_enter_current_observation():
    """A quote that claims to occur after the access cutoff is look-ahead."""
    receive = T0 + timedelta(seconds=8)
    payload = _market_payload()
    payload["currentPrice"] = {
        "value": "99999",
        "eventOccurredAt": _iso(FUTURE),
        "publishedAt": _iso(T0 - timedelta(minutes=1)),
        "sourceReceivedAt": _iso(receive),
        "tradableAt": _iso(receive),
    }
    collector = LiveMarketDataCollector(
        client=_client(
            "market",
            "https://md.example",
            FakeTransport({"/market/": (200, json.dumps(payload).encode())}),
        )
    )
    result = collector.collect("005930", receive, include_current_receive=True)
    prices = [item for item in result.items if item.kind.value == "CURRENT_PRICE"]
    assert prices == [], "future eventOccurredAt bypassed the live accessibility filter"


def test_t1_after_t0_is_in_current_observation_and_matches_final_cutoff(monkeypatch):
    _live_env(monkeypatch)
    clock = {"now": T0}

    def now() -> datetime:
        return clock["now"]

    def dart_received() -> datetime:
        clock["now"] = T0 + timedelta(seconds=45)
        return clock["now"]

    _pin_market_clock(monkeypatch, clock)
    service = build_live_observation_service(
        now_fn=now,
        market=LiveMarketDataCollector(
            client=_client(
                "market",
                "https://md.example",
                FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())}),
            )
        ),
        disclosure=LiveDisclosureCollector(
            client=_client(
                "dart",
                "https://example.test/api",
                FakeTransport({"/list.json": (200, _dart_ok_payload())}),
                "DART_API_KEY",
            ),
            received_at_fn=dart_received,
        ),
        macro=LiveMacroCollector(
            client=_client(
                "macro",
                "https://macro.example",
                FakeTransport({"/macro": (200, _quiet_macro_payload())}),
            ),
            received_at_fn=lambda: T0 + timedelta(seconds=20),
        ),
        news=LiveNewsCollector(
            client=_client(
                "news",
                "https://news.example",
                FakeTransport(
                    {
                        "/news": (
                            200,
                            json.dumps(
                                {
                                    "articles": [
                                        _news_article(
                                            title="In-cycle news",
                                            published=T0 - timedelta(minutes=5),
                                            source_received=T0 + timedelta(seconds=10),
                                        )
                                    ]
                                }
                            ).encode(),
                        )
                    }
                ),
            ),
            received_at_fn=lambda: T0 + timedelta(seconds=10),
        ),
    )
    service.llm = LiveLlmProvider(
        client=_client(
            "llm",
            "https://llm.example/v1",
            FakeTransport({"/chat/completions": (200, _llm_payload())}),
            "LLM_API_KEY",
        )
    )
    result = service.evaluate("005930")
    cutoff = result.snapshot.analysis_as_of
    assert cutoff is not None
    assert cutoff >= T0 + timedelta(seconds=45)
    assert result.envelope is not None
    assert result.envelope.analysis_as_of == cutoff
    assert result.envelope.context_fingerprint == result.snapshot.context_fingerprint
    assert result.envelope.is_order is False
    assert result.record.decision_id == result.decision_id
    assert result.record.timestamp == result.snapshot.created_at
    items = service.last_external.items if service.last_external else []
    dart_items = [item for item in items if item.source == "opendart"]
    news_items = [item for item in items if item.headline == "In-cycle news"]
    assert dart_items
    assert news_items
    for item in [*dart_items, *news_items]:
        received = item.timestamps.source_received_at
        assert received is not None
        assert received > T0
        assert received <= cutoff
        assert item.timestamps.tradable_at <= cutoff
        if item.timestamps.event_occurred_at is not None:
            assert item.timestamps.event_occurred_at <= cutoff
    assert service.last_external is not None
    assert service.last_external.as_of == cutoff


def test_explicit_past_as_of_still_hides_later_news_receive():
    past = T0
    receive = T0 + timedelta(hours=3)
    collector = LiveNewsCollector(
        client=_client(
            "news",
            "https://news.example",
            FakeTransport(
                {
                    "/news": (
                        200,
                        json.dumps(
                            {
                                "articles": [
                                    _news_article(
                                        title="Arrived later",
                                        published=T0 - timedelta(hours=1),
                                        source_received=receive,
                                    )
                                ]
                            }
                        ).encode(),
                    )
                }
            ),
        ),
        received_at_fn=lambda: receive,
    )
    result = collector.collect("005930", past, include_current_receive=False)
    assert result.items == []
    assert result.status is CollectionStatus.NO_EVENT


def test_all_provider_failure_keeps_cutoff_and_failure_status(monkeypatch):
    _live_env(monkeypatch)
    clock = {"now": T0}

    def now() -> datetime:
        return clock["now"]

    def bump() -> datetime:
        clock["now"] = clock["now"] + timedelta(seconds=5)
        return clock["now"]

    fail = _fail_transport()
    _pin_market_clock(monkeypatch, clock)
    service = build_live_observation_service(
        now_fn=now,
        market=LiveMarketDataCollector(
            client=_client("market", "https://md.example", fail)
        ),
        disclosure=LiveDisclosureCollector(
            client=_client(
                "dart",
                "https://example.test/api",
                fail,
                "DART_API_KEY",
            ),
            received_at_fn=bump,
        ),
        macro=LiveMacroCollector(
            client=_client("macro", "https://macro.example", fail),
            received_at_fn=bump,
        ),
        news=LiveNewsCollector(
            client=_client("news", "https://news.example", fail),
            received_at_fn=bump,
        ),
    )
    service.llm = LiveLlmProvider(
        client=_client("llm", "https://llm.example/v1", fail, "LLM_API_KEY")
    )
    result = service.evaluate("005930")
    cutoff = result.snapshot.analysis_as_of
    assert cutoff is not None
    assert cutoff >= T0
    assert result.market_status is CollectionStatus.DATA_UNAVAILABLE
    assert result.external_status is CollectionStatus.DATA_UNAVAILABLE
    assert result.readiness is not None
    assert result.readiness.status is DecisionReadinessStatus.BLOCKED
    assert result.envelope is not None
    assert result.envelope.analysis_as_of == cutoff
    assert result.envelope.context_fingerprint == result.snapshot.context_fingerprint
    assert result.envelope.is_order is False
    assert service.last_external is not None
    assert service.last_external.status is CollectionStatus.DATA_UNAVAILABLE
    assert service.last_external.as_of == cutoff
    names = {row.name: row.status for row in result.provider_health}
    assert names["news"] is CollectionStatus.DATA_UNAVAILABLE
    assert names["disclosure"] is CollectionStatus.DATA_UNAVAILABLE
    assert names["macro"] is CollectionStatus.DATA_UNAVAILABLE


def test_fixture_current_evaluate_keeps_pinned_cutoff():
    service = AnalysisService()
    result = service.evaluate("005930")
    assert result.data_mode is DataMode.FIXTURE
    assert result.snapshot.analysis_as_of == FIXTURE_AS_OF
    assert result.envelope is not None
    assert result.envelope.analysis_as_of == FIXTURE_AS_OF
    assert result.envelope.is_order is False


class _TickerMarket:
    """Dispatch market collect by ticker and expose the last-writer diagnostics."""

    def __init__(self, success: LiveMarketDataCollector, failure: LiveMarketDataCollector) -> None:
        self._success = success
        self._failure = failure
        self.last_diagnostics = None

    def collect(self, instrument, as_of, kinds=None, include_current_receive=False):
        target = self._success if instrument == "005930" else self._failure
        result = target.collect(
            instrument,
            as_of,
            kinds=kinds,
            include_current_receive=include_current_receive,
        )
        self.last_diagnostics = target.last_diagnostics
        return result


class _TickerLlmTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        connect_timeout: float,
        read_timeout: float,
    ) -> tuple[int, bytes]:
        text = (body or b"").decode()
        self.calls.append(text)
        if '"000660"' in text or "000660" in text:
            return 200, json.dumps(
                {"model": "gpt-test", "choices": [{"message": {"content": "not-json{{{"}}]}
            ).encode()
        return 200, _llm_payload()


def test_concurrent_evaluate_responses_stay_on_own_execution(monkeypatch):
    """Cross collect-complete and diagnostics-write on the shared app service."""
    _live_env(monkeypatch)
    clock = {"now": T0}
    _pin_market_clock(monkeypatch, clock)

    market_ok = LiveMarketDataCollector(
        client=_client(
            "market",
            "https://md.example",
            FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())}),
        )
    )
    market_fail = LiveMarketDataCollector(
        client=_client(
            "market-b",
            "https://md.example",
            FakeTransport({"/market/": (500, b'{"error":"ticker-b-fail"}')}),
        )
    )
    a_collected = threading.Event()
    b_diagnostics_written = threading.Event()
    b_captured = threading.Event()

    class InterleavedMarket(_TickerMarket):
        def collect(self, instrument, as_of, kinds=None, include_current_receive=False):
            if instrument == "005930":
                result = self._success.collect(
                    instrument,
                    as_of,
                    kinds=kinds,
                    include_current_receive=include_current_receive,
                )
                self.last_diagnostics = self._success.last_diagnostics
                a_collected.set()
                assert b_diagnostics_written.wait(timeout=5), "B did not write market diagnostics"
                return result
            assert a_collected.wait(timeout=5), "A did not finish market collect"
            result = self._failure.collect(
                instrument,
                as_of,
                kinds=kinds,
                include_current_receive=include_current_receive,
            )
            self.last_diagnostics = self._failure.last_diagnostics
            b_diagnostics_written.set()
            return result

    quiet_news = LiveNewsCollector(
        client=_client(
            "news",
            "https://news.example",
            FakeTransport({"/news": (200, _quiet_news_payload())}),
        ),
        received_at_fn=lambda: T0,
    )
    quiet_macro = LiveMacroCollector(
        client=_client(
            "macro",
            "https://macro.example",
            FakeTransport({"/macro": (200, _quiet_macro_payload())}),
        ),
        received_at_fn=lambda: T0,
    )
    dart = LiveDisclosureCollector(
        client=_client(
            "dart",
            "https://example.test/api",
            FakeTransport({"/list.json": (200, _dart_empty_payload())}),
            "DART_API_KEY",
        ),
        received_at_fn=lambda: T0,
    )
    llm_transport = _TickerLlmTransport()
    service = build_live_observation_service(
        now_fn=lambda: clock["now"],
        market=InterleavedMarket(market_ok, market_fail),
        disclosure=dart,
        macro=quiet_macro,
        news=quiet_news,
    )
    service.llm = LiveLlmProvider(
        client=_client("llm", "https://llm.example/v1", llm_transport, "LLM_API_KEY")
    )
    original_capture = service._capture_provider_diagnostics

    def interleaved_capture(news, disclosure, macro):
        name = threading.current_thread().name
        if name == "eval-A":
            assert b_captured.wait(timeout=5), "B did not capture diagnostics first"
        original_capture(news, disclosure, macro)
        if name == "eval-B":
            b_captured.set()

    service._capture_provider_diagnostics = interleaved_capture
    app = create_app(service)
    assert app.state.analysis is service

    results: dict[str, object] = {}
    errors: dict[str, BaseException] = {}

    def run_eval(label: str, ticker: str) -> None:
        try:
            results[label] = app.state.analysis.evaluate(ticker)
        except BaseException as exc:
            errors[label] = exc

    thread_a = threading.Thread(target=run_eval, args=("A", "005930"), name="eval-A")
    thread_b = threading.Thread(target=run_eval, args=("B", "000660"), name="eval-B")
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=8)
    thread_b.join(timeout=8)
    assert not thread_a.is_alive() and not thread_b.is_alive()
    assert errors == {}, errors

    result_a = results["A"]
    result_b = results["B"]
    assert result_a.ticker == "005930"
    assert result_b.ticker == "000660"
    assert result_a.decision_id != result_b.decision_id
    assert result_a.envelope is not None and result_b.envelope is not None
    assert result_a.envelope.proposal_id == result_a.decision_id
    assert result_b.envelope.proposal_id == result_b.decision_id
    assert result_a.record.decision_id == result_a.decision_id
    assert result_b.record.decision_id == result_b.decision_id
    assert result_a.record.ticker == "005930"
    assert result_b.record.ticker == "000660"
    assert result_a.market_status is CollectionStatus.OK
    assert result_b.market_status is CollectionStatus.DATA_UNAVAILABLE
    assert result_a.readiness is not None and result_b.readiness is not None
    assert result_a.readiness.status is not DecisionReadinessStatus.BLOCKED
    assert result_b.readiness.status is DecisionReadinessStatus.BLOCKED
    assert "MARKET_DATA_UNAVAILABLE" in result_b.readiness.reason_codes
    assert "MARKET_DATA_UNAVAILABLE" not in result_a.readiness.reason_codes
    assert result_a.envelope.is_order is False
    assert result_b.envelope.is_order is False
    thesis_a = result_a.envelope.thesis.headline
    thesis_b = result_b.envelope.thesis.headline
    assert thesis_a != "LLM unavailable"
    assert thesis_b == "LLM unavailable"
    stored = {item.decision_id: item for item in service.list_decisions()}
    assert result_a.decision_id in stored
    assert result_b.decision_id in stored
    assert stored[result_a.decision_id].ticker == "005930"
    assert stored[result_b.decision_id].ticker == "000660"

    # Shared last_* / collector diagnostics / health are process-level last-writer,
    # not request-scoped. They must not be read as "the request you just made".
    assert service.last_market is not None
    last_instruments = {item.instrument for item in service.last_market.items}
    if service.last_market.items:
        assert last_instruments <= {"005930", "000660"}
    health = collect_health(service)
    assert health.event_pipeline_health.detail == "event intelligence pipeline last run succeeded"
    assert health.llm_health is not None


def test_health_last_run_is_process_level_not_request_scoped(monkeypatch):
    _live_env(monkeypatch)
    service = build_live_observation_service(
        now_fn=lambda: T0,
        market=LiveMarketDataCollector(
            client=_client(
                "market",
                "https://md.example",
                FakeTransport({"/market/": (200, json.dumps(_market_payload()).encode())}),
            )
        ),
        disclosure=LiveDisclosureCollector(
            client=_client(
                "dart",
                "https://example.test/api",
                FakeTransport({"/list.json": (200, _dart_empty_payload())}),
                "DART_API_KEY",
            ),
            received_at_fn=lambda: T0,
        ),
        macro=LiveMacroCollector(
            client=_client(
                "macro",
                "https://macro.example",
                FakeTransport({"/macro": (200, _quiet_macro_payload())}),
            ),
            received_at_fn=lambda: T0,
        ),
        news=LiveNewsCollector(
            client=_client(
                "news",
                "https://news.example",
                FakeTransport({"/news": (200, _quiet_news_payload())}),
            ),
            received_at_fn=lambda: T0,
        ),
    )
    service.llm = LiveLlmProvider(
        client=_client(
            "llm",
            "https://llm.example/v1",
            FakeTransport({"/chat/completions": (200, _llm_payload())}),
            "LLM_API_KEY",
        )
    )
    first = service.evaluate("005930", as_of=T0)
    health = collect_health(service)
    assert first.decision_id
    assert service.last_market is not None
    assert service.last_market.status is CollectionStatus.OK
    assert health.event_pipeline_health.detail == "event intelligence pipeline last run succeeded"
    # collect_health re-collects news/disclosure/macro/scheduled and uses
    # last_market when present. That snapshot is process-level last-writer,
    # not a per-request handle.
    assert "has not run" not in health.event_pipeline_health.detail
