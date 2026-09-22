"""10.5.1 Provider Framework: timeout, retry, circuit, secret masking."""

from __future__ import annotations

import os
from typing import Mapping

import pytest

from ai_investment_agent.adapters.live.config import (
    CircuitBreakerConfig,
    HttpTimeoutConfig,
    ProviderHttpConfig,
    RateLimitConfig,
    RetryConfig,
    mask_secrets,
    market_http_config,
)
from ai_investment_agent.adapters.live.diagnostics import ProviderDiagnostics
from ai_investment_agent.adapters.live.http import ProviderHttpClient, ProviderHttpError
from ai_investment_agent.domain.enums import CollectionStatus


class FakeTransport:
    def __init__(self, responses: list[tuple[int, bytes] | Exception]) -> None:
        self.responses = list(responses)
        self.calls = 0

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
        self.calls += 1
        if not self.responses:
            raise AssertionError("no more fake responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _config(**overrides: object) -> ProviderHttpConfig:
    base = ProviderHttpConfig(
        name="market",
        base_url="https://example.test",
        api_key_env="MARKET_DATA_API_KEY",
        timeout=HttpTimeoutConfig(connect_seconds=0.1, read_seconds=0.1, total_seconds=5.0),
        retry=RetryConfig(max_attempts=3, base_backoff_seconds=0.0, max_backoff_seconds=0.0),
        rate_limit=RateLimitConfig(max_requests_per_second=1000.0),
        circuit=CircuitBreakerConfig(failure_threshold=3, cooldown_seconds=60.0),
    )
    return ProviderHttpConfig(**{**base.__dict__, **overrides})


def test_timeout_raises_data_unavailable_error_code():
    transport = FakeTransport(
        [ProviderHttpError("timeout", error_code="TIMEOUT", retryable=True)]
    )
    client = ProviderHttpClient(config=_config(retry=RetryConfig(max_attempts=1)), transport=transport)
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/quote")
    assert exc.value.error_code == "TIMEOUT"
    assert transport.calls == 1


def test_429_retries_then_fails():
    transport = FakeTransport(
        [
            (429, b'{"error":"rate"}'),
            (429, b'{"error":"rate"}'),
            (429, b'{"error":"rate"}'),
        ]
    )
    client = ProviderHttpClient(config=_config(), transport=transport)
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/quote")
    assert exc.value.status_code == 429
    assert transport.calls == 3
    assert client.last_attempt_count == 3


def test_401_does_not_retry():
    transport = FakeTransport([(401, b'{"error":"unauthorized"}')])
    client = ProviderHttpClient(config=_config(), transport=transport)
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/quote")
    assert exc.value.status_code == 401
    assert exc.value.retryable is False
    assert transport.calls == 1


def test_403_does_not_retry():
    transport = FakeTransport([(403, b'{"error":"forbidden"}')])
    client = ProviderHttpClient(config=_config(), transport=transport)
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/quote")
    assert exc.value.status_code == 403
    assert transport.calls == 1


def test_circuit_opens_after_repeated_failures():
    transport = FakeTransport(
        [
            (500, b"err"),
            (500, b"err"),
            (500, b"err"),
        ]
    )
    cfg = _config(
        retry=RetryConfig(max_attempts=1, base_backoff_seconds=0.0),
        circuit=CircuitBreakerConfig(failure_threshold=2, cooldown_seconds=60.0),
    )
    client = ProviderHttpClient(config=cfg, transport=transport)
    client.sleep_fn = lambda _s: None
    with pytest.raises(ProviderHttpError):
        client.get_json("/a")
    with pytest.raises(ProviderHttpError):
        client.get_json("/b")
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/c")
    assert exc.value.error_code == "CIRCUIT_OPEN"
    assert transport.calls == 2


def test_mask_secrets_redacts_env_values(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-value-12345678")
    text = "Authorization: Bearer sk-secret-value-12345678 failed"
    assert "sk-secret-value-12345678" not in mask_secrets(text)
    assert "LLM_API_KEY_REDACTED" in mask_secrets(text)


def test_provider_http_error_masks_secret_in_message(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dart-secret-abcdefgh")
    err = ProviderHttpError("failed with dart-secret-abcdefgh")
    assert "dart-secret-abcdefgh" not in str(err)


def test_diagnostics_statuses_are_explicit():
    ok = ProviderDiagnostics.ok(provider="market")
    no_event = ProviderDiagnostics.no_event(provider="news")
    unavailable = ProviderDiagnostics.unavailable(
        provider="dart",
        error_code="TIMEOUT",
        error_message="timeout",
    )
    degraded = ProviderDiagnostics.degraded(
        provider="macro",
        error_code="HTTP_429",
        error_message="rate limited",
    )
    assert ok.status is CollectionStatus.OK
    assert no_event.status is CollectionStatus.NO_EVENT
    assert unavailable.status is CollectionStatus.DATA_UNAVAILABLE
    assert degraded.status is CollectionStatus.DEGRADED
    assert unavailable.status is not CollectionStatus.NO_EVENT


def test_not_configured_base_url():
    client = ProviderHttpClient(config=_config(base_url=""))
    with pytest.raises(ProviderHttpError) as exc:
        client.get_json("/x")
    assert exc.value.error_code == "NOT_CONFIGURED"


def test_market_config_reads_env(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_BASE_URL", "https://md.example/")
    monkeypatch.setenv("MARKET_DATA_RPS", "3.5")
    cfg = market_http_config()
    assert cfg.base_url == "https://md.example"
    assert cfg.rate_limit.max_requests_per_second == 3.5
    assert cfg.api_key_env == "MARKET_DATA_API_KEY"
