"""10.5.8 HTTP decode/timeout/circuit hardening (deterministic clocks)."""

from __future__ import annotations

import pytest

from ai_investment_agent.adapters.live.config import (
    CircuitBreakerConfig,
    HttpTimeoutConfig,
    RateLimitConfig,
    RetryConfig,
    mask_secrets,
)
from ai_investment_agent.adapters.live.errors import result_from_http_error
from ai_investment_agent.adapters.live.http import (
    ProviderHttpClient,
    ProviderHttpError,
    UrlLibTransport,
)
from ai_investment_agent.adapters.live.market import LiveMarketDataCollector
from ai_investment_agent.domain.enums import CollectionStatus
from tests.test_provider_framework import FakeTransport, _config
from datetime import datetime, timezone


def test_http_200_html_is_provider_error_not_raw_exception():
    client = ProviderHttpClient(
        config=_config(retry=RetryConfig(max_attempts=1)),
        transport=FakeTransport([(200, b"<html>oops</html>")]),
    )
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/quote")
    assert exc.value.error_code == "INVALID_JSON"
    assert "<html>" not in str(exc.value)


def test_invalid_json_and_invalid_utf8():
    json_client = ProviderHttpClient(
        config=_config(retry=RetryConfig(max_attempts=1)),
        transport=FakeTransport([(200, b"{not json")]),
    )
    json_client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError) as exc:
        json_client.get_json("/quote")
    assert exc.value.error_code == "INVALID_JSON"

    utf_client = ProviderHttpClient(
        config=_config(retry=RetryConfig(max_attempts=1)),
        transport=FakeTransport([(200, b"\xff\xfe")]),
    )
    utf_client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError) as exc:
        utf_client.get_json("/quote")
    assert exc.value.error_code == "INVALID_ENCODING"


def test_json_success_recorded_only_after_parse():
    transport = FakeTransport([(200, b"<html>")])
    client = ProviderHttpClient(
        config=_config(
            retry=RetryConfig(max_attempts=1),
            circuit=CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=30.0),
        ),
        transport=transport,
    )
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError):
        client.get_json("/quote")
    assert client.circuit.failures == 1
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/quote")
    assert exc.value.error_code == "CIRCUIT_OPEN"


def test_401_records_single_circuit_failure():
    client = ProviderHttpClient(
        config=_config(
            retry=RetryConfig(max_attempts=3),
            circuit=CircuitBreakerConfig(failure_threshold=5, cooldown_seconds=30.0),
        ),
        transport=FakeTransport([(401, b'{"error":"no"}')]),
    )
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError):
        client.get_json("/quote")
    assert client.circuit.failures == 1


def test_deadline_during_rate_limit_wait():
    clock = [0.0]

    def mono() -> float:
        return clock[0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    cfg = _config(
        timeout=HttpTimeoutConfig(total_seconds=0.2, connect_seconds=1.0, read_seconds=1.0),
        rate_limit=RateLimitConfig(max_requests_per_second=1.0),
        retry=RetryConfig(max_attempts=2, base_backoff_seconds=0.0),
    )
    transport = FakeTransport([(200, b'{"ok":true}'), (200, b'{"ok":true}')])
    client = ProviderHttpClient(config=cfg, transport=transport, monotonic_fn=mono, sleep_fn=sleep)
    client.get_json("/a")
    clock[0] = 0.05
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/b")
    assert exc.value.error_code == "TIMEOUT"
    assert transport.calls == 1


def test_transport_timeouts_are_clamped_to_remaining():
    clock = [0.0]
    seen: list[tuple[float, float]] = []

    class RecordingTransport:
        def request(self, method, url, *, headers, body, connect_timeout, read_timeout):
            seen.append((connect_timeout, read_timeout))
            return 200, b'{"ok":true}'

    cfg = _config(
        timeout=HttpTimeoutConfig(total_seconds=1.0, connect_seconds=5.0, read_seconds=5.0),
        rate_limit=RateLimitConfig(max_requests_per_second=0),
        retry=RetryConfig(max_attempts=1),
    )
    client = ProviderHttpClient(
        config=cfg,
        transport=RecordingTransport(),
        monotonic_fn=lambda: clock[0],
        sleep_fn=lambda _s: None,
    )
    client.get_json("/x")
    assert seen
    assert seen[0][0] <= 1.0
    assert seen[0][1] <= 1.0


def test_circuit_cooldown_recovers_with_injected_clock():
    clock = [10.0]
    transport = FakeTransport(
        [
            (500, b"err"),
            (500, b"err"),
            (200, b'{"ok":true}'),
        ]
    )
    cfg = _config(
        retry=RetryConfig(max_attempts=1, base_backoff_seconds=0.0),
        circuit=CircuitBreakerConfig(failure_threshold=2, cooldown_seconds=30.0),
    )
    client = ProviderHttpClient(
        config=cfg,
        transport=transport,
        monotonic_fn=lambda: clock[0],
        sleep_fn=lambda _s: None,
    )
    with pytest.raises(ProviderHttpError):
        client.get_json("/a")
    with pytest.raises(ProviderHttpError):
        client.get_json("/b")
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/c")
    assert exc.value.error_code == "CIRCUIT_OPEN"
    clock[0] = 50.0
    payload = client.get_json("/d")
    assert payload == {"ok": True}


def test_no_network_blocks_real_urllib_transport(monkeypatch):
    monkeypatch.setenv("NO_NETWORK", "1")
    transport = UrlLibTransport()
    with pytest.raises(ProviderHttpError) as exc:
        transport.request(
            "GET",
            "https://example.invalid/quote",
            headers={},
            body=None,
            connect_timeout=0.1,
            read_timeout=0.1,
        )
    assert exc.value.error_code == "NETWORK_BLOCKED"


def test_html_market_response_is_unavailable_not_no_event():
    collector = LiveMarketDataCollector(
        client=ProviderHttpClient(
            config=_config(base_url="https://md.example", retry=RetryConfig(max_attempts=1)),
            transport=FakeTransport([(200, b"<html>nope</html>")]),
        )
    )
    collector._client.sleep_fn = lambda _s: None
    result = collector.collect("005930", datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc))
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert result.status is not CollectionStatus.NO_EVENT


def test_http_error_maps_to_unavailable_diagnostics():
    err = ProviderHttpError("invalid json", error_code="INVALID_JSON")
    as_of = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
    result, diagnostics = result_from_http_error(
        err,
        as_of=as_of,
        provider="market",
        requested_at=as_of,
        received_at=as_of,
        attempt_count=1,
        circuit_open=False,
    )
    assert result.status is CollectionStatus.DATA_UNAVAILABLE
    assert diagnostics.error_code == "INVALID_JSON"


def test_mask_secrets_redacts_query_keys(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-secret-abcdefgh")
    text = "failed crtfc_key=dart-secret-abcdefgh Authorization: Bearer dart-secret-abcdefgh"
    masked = mask_secrets(text)
    assert "dart-secret-abcdefgh" not in masked
    assert "crtfc_key=[REDACTED]" in masked


