"""Shared HTTP transport with timeout, bounded retry, rate limit, circuit breaker.

Domain code must not import httpx/SDK vendors directly — adapters use this client.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai_investment_agent.adapters.live.config import (
    ProviderHttpConfig,
    mask_secrets,
)


class ProviderHttpError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str = "HTTP_ERROR",
        retryable: bool = False,
    ) -> None:
        super().__init__(mask_secrets(message))
        self.status_code = status_code
        self.error_code = error_code
        self.retryable = retryable


class Transport(Protocol):
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
        ...


class UrlLibTransport:
    """Stdlib transport so Domain stays free of vendor SDKs."""

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
        req = Request(url, data=body, headers=dict(headers), method=method)
        timeout = max(connect_timeout, read_timeout)
        try:
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — adapter boundary
                return int(resp.status), resp.read()
        except HTTPError as exc:
            payload = exc.read() if hasattr(exc, "read") else b""
            raise ProviderHttpError(
                f"HTTP {exc.code}",
                status_code=int(exc.code),
                error_code=f"HTTP_{exc.code}",
                retryable=int(exc.code) in {429, 500, 502, 503, 504},
            ) from exc
        except URLError as exc:
            raise ProviderHttpError(
                f"network error: {exc.reason}",
                error_code="NETWORK_ERROR",
                retryable=True,
            ) from exc
        except TimeoutError as exc:
            raise ProviderHttpError(
                "timeout",
                error_code="TIMEOUT",
                retryable=True,
            ) from exc


@dataclass
class CircuitBreaker:
    failure_threshold: int
    cooldown_seconds: float
    failures: int = 0
    opened_at: float | None = None

    def allow(self, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        if self.opened_at is None:
            return True
        if moment - self.opened_at >= self.cooldown_seconds:
            self.opened_at = None
            self.failures = 0
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self, now: float | None = None) -> None:
        moment = time.monotonic() if now is None else now
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = moment

    @property
    def is_open(self) -> bool:
        return self.opened_at is not None and not self.allow()


@dataclass
class RateLimiter:
    max_requests_per_second: float
    _last_at: float = 0.0

    def wait(self, sleep_fn: Callable[[float], None] = time.sleep) -> None:
        if self.max_requests_per_second <= 0:
            return
        min_interval = 1.0 / self.max_requests_per_second
        now = time.monotonic()
        delta = now - self._last_at
        if delta < min_interval:
            sleep_fn(min_interval - delta)
        self._last_at = time.monotonic()


@dataclass
class ProviderHttpClient:
    config: ProviderHttpConfig
    transport: Transport = field(default_factory=UrlLibTransport)
    sleep_fn: Callable[[float], None] = time.sleep
    monotonic_fn: Callable[[], float] = time.monotonic
    circuit: CircuitBreaker = field(init=False)
    rate_limiter: RateLimiter = field(init=False)
    last_attempt_count: int = 0

    def __post_init__(self) -> None:
        self.circuit = CircuitBreaker(
            failure_threshold=self.config.circuit.failure_threshold,
            cooldown_seconds=self.config.circuit.cooldown_seconds,
        )
        self.rate_limiter = RateLimiter(self.config.rate_limit.max_requests_per_second)

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return self.request_json("GET", path, params=params, headers=headers, body=None)

    def post_json(
        self,
        path: str,
        *,
        payload: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return self.request_json(
            "POST",
            path,
            params=None,
            headers=headers,
            body=json.dumps(payload).encode("utf-8"),
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        body: bytes | None,
    ) -> Any:
        if not self.config.base_url:
            raise ProviderHttpError(
                f"{self.config.name} base URL is not configured",
                error_code="NOT_CONFIGURED",
                retryable=False,
            )
        if not self.circuit.allow(self.monotonic_fn()):
            raise ProviderHttpError(
                f"{self.config.name} circuit open",
                error_code="CIRCUIT_OPEN",
                retryable=False,
            )

        url = self._url(path, params)
        hdrs = {"Accept": "application/json", "User-Agent": "ai-investment-agent/0.1"}
        if headers:
            hdrs.update(headers)
        api_key = self.config.api_key()
        if api_key:
            hdrs.setdefault("Authorization", f"Bearer {api_key}")
        if body is not None:
            hdrs.setdefault("Content-Type", "application/json")

        attempt = 0
        last_error: ProviderHttpError | None = None
        started = self.monotonic_fn()
        deadline = started + self.config.timeout.total_seconds

        while attempt < self.config.retry.max_attempts:
            attempt += 1
            self.last_attempt_count = attempt
            if self.monotonic_fn() > deadline:
                last_error = ProviderHttpError(
                    "total timeout exceeded",
                    error_code="TIMEOUT",
                    retryable=False,
                )
                break
            self.rate_limiter.wait(self.sleep_fn)
            try:
                status, raw = self.transport.request(
                    method,
                    url,
                    headers=hdrs,
                    body=body,
                    connect_timeout=self.config.timeout.connect_seconds,
                    read_timeout=self.config.timeout.read_seconds,
                )
                if status in self.config.retry.no_retry_statuses:
                    self.circuit.record_failure(self.monotonic_fn())
                    raise ProviderHttpError(
                        f"HTTP {status}",
                        status_code=status,
                        error_code=f"HTTP_{status}",
                        retryable=False,
                    )
                if status in self.config.retry.retry_statuses:
                    raise ProviderHttpError(
                        f"HTTP {status}",
                        status_code=status,
                        error_code=f"HTTP_{status}",
                        retryable=True,
                    )
                if status < 200 or status >= 300:
                    self.circuit.record_failure(self.monotonic_fn())
                    raise ProviderHttpError(
                        f"HTTP {status}",
                        status_code=status,
                        error_code=f"HTTP_{status}",
                        retryable=False,
                    )
                self.circuit.record_success()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
            except ProviderHttpError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self.config.retry.max_attempts:
                    self.circuit.record_failure(self.monotonic_fn())
                    raise
                backoff = min(
                    self.config.retry.max_backoff_seconds,
                    self.config.retry.base_backoff_seconds * (2 ** (attempt - 1)),
                )
                self.sleep_fn(backoff)

        assert last_error is not None
        self.circuit.record_failure(self.monotonic_fn())
        raise last_error

    def _url(self, path: str, params: Mapping[str, str] | None) -> str:
        base = self.config.base_url.rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}"
        url = f"{base}{suffix}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url
