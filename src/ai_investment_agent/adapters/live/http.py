"""Shared HTTP transport with timeout, bounded retry, rate limit, circuit breaker.

Domain code must not import httpx/SDK vendors directly — adapters use this client.

Timeout budget
--------------
``total_seconds`` is a monotonic deadline covering rate-limit wait, backoff,
and transport. Remaining time is clamped onto connect/read timeouts.
``UrlLibTransport`` cannot abort a socket that keeps delivering bytes after
that deadline; a late completion is rejected and is not a circuit success.
Circuit failures are counted once per attempt (not once per raise site).
JSON is parsed before the attempt is treated as a circuit success.
"""

from __future__ import annotations

import json
import os
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
        if os.environ.get("NO_NETWORK") == "1":
            raise ProviderHttpError(
                "NO_NETWORK=1 blocked real transport",
                error_code="NETWORK_BLOCKED",
                retryable=False,
            )
        req = Request(url, data=body, headers=dict(headers), method=method)
        timeout = max(connect_timeout, read_timeout)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return int(resp.status), resp.read()
        except HTTPError as exc:
            _ = exc.read() if hasattr(exc, "read") else b""
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
    """Failure unit: one record_failure per HTTP attempt.

    Opens when failures reach ``failure_threshold``. Cooldown uses the
    injected monotonic clock passed to ``allow`` / ``record_failure``.
    """

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
    monotonic_fn: Callable[[], float] = time.monotonic
    _last_at: float | None = None

    def required_wait(self) -> float:
        if self.max_requests_per_second <= 0:
            return 0.0
        if self._last_at is None:
            return 0.0
        min_interval = 1.0 / self.max_requests_per_second
        delta = self.monotonic_fn() - self._last_at
        return max(0.0, min_interval - delta)

    def mark(self) -> None:
        self._last_at = self.monotonic_fn()

    def wait(self, sleep_fn: Callable[[float], None] = time.sleep) -> None:
        delay = self.required_wait()
        if delay > 0:
            sleep_fn(delay)
        self.mark()


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
        self.rate_limiter = RateLimiter(
            self.config.rate_limit.max_requests_per_second,
            monotonic_fn=self.monotonic_fn,
        )

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
        self.rate_limiter.monotonic_fn = self.monotonic_fn

        while attempt < self.config.retry.max_attempts:
            attempt += 1
            self.last_attempt_count = attempt
            now = self.monotonic_fn()
            remaining = deadline - now
            if remaining <= 0:
                last_error = ProviderHttpError(
                    "total timeout exceeded",
                    error_code="TIMEOUT",
                    retryable=False,
                )
                self.circuit.record_failure(now)
                break

            wait = self.rate_limiter.required_wait()
            if wait > remaining:
                last_error = ProviderHttpError(
                    "deadline exhausted while rate-limiting",
                    error_code="TIMEOUT",
                    retryable=False,
                )
                self.circuit.record_failure(self.monotonic_fn())
                break
            if wait > 0:
                self.sleep_fn(wait)
                remaining = deadline - self.monotonic_fn()
                if remaining <= 0:
                    last_error = ProviderHttpError(
                        "deadline exhausted while rate-limiting",
                        error_code="TIMEOUT",
                        retryable=False,
                    )
                    self.circuit.record_failure(self.monotonic_fn())
                    break
            self.rate_limiter.mark()

            connect_timeout = min(self.config.timeout.connect_seconds, max(remaining, 0.001))
            read_timeout = min(self.config.timeout.read_seconds, max(remaining, 0.001))
            try:
                status, raw = self.transport.request(
                    method,
                    url,
                    headers=hdrs,
                    body=body,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )
                if self.monotonic_fn() > deadline:
                    raise ProviderHttpError(
                        "deadline exceeded before response accepted",
                        error_code="TIMEOUT",
                        retryable=False,
                    )
                if status in self.config.retry.no_retry_statuses:
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
                    raise ProviderHttpError(
                        f"HTTP {status}",
                        status_code=status,
                        error_code=f"HTTP_{status}",
                        retryable=False,
                    )
                parsed = _parse_json_body(raw)
                self.circuit.record_success()
                return parsed
            except ProviderHttpError as exc:
                last_error = exc
                self.circuit.record_failure(self.monotonic_fn())
                if not exc.retryable or attempt >= self.config.retry.max_attempts:
                    raise
                now = self.monotonic_fn()
                remaining = deadline - now
                backoff = min(
                    self.config.retry.max_backoff_seconds,
                    self.config.retry.base_backoff_seconds * (2 ** (attempt - 1)),
                )
                if backoff > remaining:
                    raise ProviderHttpError(
                        "deadline exhausted during backoff",
                        error_code="TIMEOUT",
                        retryable=False,
                    ) from exc
                self.sleep_fn(backoff)

        assert last_error is not None
        raise last_error

    def _url(self, path: str, params: Mapping[str, str] | None) -> str:
        base = self.config.base_url.rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}"
        url = f"{base}{suffix}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url


def _parse_json_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProviderHttpError(
            "invalid utf-8 in provider response",
            error_code="INVALID_ENCODING",
            retryable=False,
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderHttpError(
            "invalid json in provider response",
            error_code="INVALID_JSON",
            retryable=False,
        ) from exc
