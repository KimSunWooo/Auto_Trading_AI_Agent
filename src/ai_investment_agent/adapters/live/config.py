"""Live provider configuration from environment only. Never hard-code secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class HttpTimeoutConfig:
    connect_seconds: float = 3.0
    read_seconds: float = 10.0
    total_seconds: float = 15.0


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 4.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    no_retry_statuses: tuple[int, ...] = (400, 401, 403, 404, 422)


@dataclass(frozen=True)
class RateLimitConfig:
    max_requests_per_second: float = 2.0


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    cooldown_seconds: float = 30.0


@dataclass(frozen=True)
class ProviderHttpConfig:
    name: str
    base_url: str
    api_key_env: str | None
    timeout: HttpTimeoutConfig
    retry: RetryConfig
    rate_limit: RateLimitConfig
    circuit: CircuitBreakerConfig

    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        value = os.environ.get(self.api_key_env)
        if value is None or value.strip() == "":
            return None
        return value.strip()


def market_http_config() -> ProviderHttpConfig:
    return ProviderHttpConfig(
        name="market",
        base_url=os.environ.get("MARKET_DATA_BASE_URL", "").rstrip("/"),
        api_key_env="MARKET_DATA_API_KEY",
        timeout=HttpTimeoutConfig(
            connect_seconds=_float("MARKET_DATA_CONNECT_TIMEOUT", 3.0),
            read_seconds=_float("MARKET_DATA_READ_TIMEOUT", 10.0),
            total_seconds=_float("MARKET_DATA_TOTAL_TIMEOUT", 15.0),
        ),
        retry=RetryConfig(max_attempts=_int("MARKET_DATA_MAX_RETRIES", 3)),
        rate_limit=RateLimitConfig(
            max_requests_per_second=_float("MARKET_DATA_RPS", 2.0),
        ),
        circuit=CircuitBreakerConfig(
            failure_threshold=_int("MARKET_DATA_CIRCUIT_FAILURES", 5),
            cooldown_seconds=_float("MARKET_DATA_CIRCUIT_COOLDOWN", 30.0),
        ),
    )


def dart_http_config() -> ProviderHttpConfig:
    return ProviderHttpConfig(
        name="dart",
        base_url=os.environ.get(
            "DART_BASE_URL",
            "https://opendart.fss.or.kr/api",
        ).rstrip("/"),
        api_key_env="DART_API_KEY",
        timeout=HttpTimeoutConfig(
            connect_seconds=_float("DART_CONNECT_TIMEOUT", 3.0),
            read_seconds=_float("DART_READ_TIMEOUT", 10.0),
            total_seconds=_float("DART_TOTAL_TIMEOUT", 15.0),
        ),
        retry=RetryConfig(max_attempts=_int("DART_MAX_RETRIES", 3)),
        rate_limit=RateLimitConfig(max_requests_per_second=_float("DART_RPS", 1.0)),
        circuit=CircuitBreakerConfig(
            failure_threshold=_int("DART_CIRCUIT_FAILURES", 5),
            cooldown_seconds=_float("DART_CIRCUIT_COOLDOWN", 60.0),
        ),
    )


def macro_http_config() -> ProviderHttpConfig:
    return ProviderHttpConfig(
        name="macro",
        base_url=os.environ.get("MACRO_BASE_URL", "").rstrip("/"),
        api_key_env="MACRO_API_KEY",
        timeout=HttpTimeoutConfig(
            connect_seconds=_float("MACRO_CONNECT_TIMEOUT", 3.0),
            read_seconds=_float("MACRO_READ_TIMEOUT", 10.0),
            total_seconds=_float("MACRO_TOTAL_TIMEOUT", 15.0),
        ),
        retry=RetryConfig(max_attempts=_int("MACRO_MAX_RETRIES", 3)),
        rate_limit=RateLimitConfig(max_requests_per_second=_float("MACRO_RPS", 1.0)),
        circuit=CircuitBreakerConfig(
            failure_threshold=_int("MACRO_CIRCUIT_FAILURES", 5),
            cooldown_seconds=_float("MACRO_CIRCUIT_COOLDOWN", 60.0),
        ),
    )


def news_http_config() -> ProviderHttpConfig:
    return ProviderHttpConfig(
        name="news",
        base_url=os.environ.get("NEWS_BASE_URL", "").rstrip("/"),
        api_key_env="NEWS_API_KEY",
        timeout=HttpTimeoutConfig(
            connect_seconds=_float("NEWS_CONNECT_TIMEOUT", 3.0),
            read_seconds=_float("NEWS_READ_TIMEOUT", 10.0),
            total_seconds=_float("NEWS_TOTAL_TIMEOUT", 15.0),
        ),
        retry=RetryConfig(max_attempts=_int("NEWS_MAX_RETRIES", 3)),
        rate_limit=RateLimitConfig(max_requests_per_second=_float("NEWS_RPS", 1.0)),
        circuit=CircuitBreakerConfig(
            failure_threshold=_int("NEWS_CIRCUIT_FAILURES", 5),
            cooldown_seconds=_float("NEWS_CIRCUIT_COOLDOWN", 60.0),
        ),
    )


def llm_http_config() -> ProviderHttpConfig:
    return ProviderHttpConfig(
        name="llm",
        base_url=os.environ.get(
            "LLM_BASE_URL",
            "https://api.openai.com/v1",
        ).rstrip("/"),
        api_key_env="LLM_API_KEY",
        timeout=HttpTimeoutConfig(
            connect_seconds=_float("LLM_CONNECT_TIMEOUT", 3.0),
            read_seconds=_float("LLM_READ_TIMEOUT", 45.0),
            total_seconds=_float("LLM_TOTAL_TIMEOUT", 60.0),
        ),
        retry=RetryConfig(max_attempts=_int("LLM_MAX_RETRIES", 2)),
        rate_limit=RateLimitConfig(max_requests_per_second=_float("LLM_RPS", 1.0)),
        circuit=CircuitBreakerConfig(
            failure_threshold=_int("LLM_CIRCUIT_FAILURES", 3),
            cooldown_seconds=_float("LLM_CIRCUIT_COOLDOWN", 45.0),
        ),
    )


SECRET_ENV_NAMES = (
    "DART_API_KEY",
    "MARKET_DATA_API_KEY",
    "NEWS_API_KEY",
    "MACRO_API_KEY",
    "LLM_API_KEY",
)


def mask_secrets(text: str) -> str:
    """Redact known secret values from log/exception text."""
    masked = text
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value and len(value) >= 8:
            masked = masked.replace(value, f"[{name}_REDACTED]")
    return masked
