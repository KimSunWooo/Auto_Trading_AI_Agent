"""Shared helpers for live collectors. Never map outages to NO_EVENT."""

from __future__ import annotations

from datetime import datetime

from ai_investment_agent.adapters.live.diagnostics import ProviderDiagnostics
from ai_investment_agent.adapters.live.http import ProviderHttpError
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass


def result_from_http_error(
    exc: ProviderHttpError,
    *,
    as_of: datetime,
    provider: str,
    requested_at: datetime,
    received_at: datetime,
    attempt_count: int,
    circuit_open: bool,
    freshness_class: FreshnessClass | None = None,
) -> tuple[CollectionResult, ProviderDiagnostics]:
    """Map transport failures to DATA_UNAVAILABLE or DEGRADED — never NO_EVENT."""
    latency_ms = (received_at - requested_at).total_seconds() * 1000.0
    code = exc.error_code
    if code == "CIRCUIT_OPEN" or (exc.status_code is not None and exc.status_code == 429):
        diagnostics = ProviderDiagnostics.degraded(
            provider=provider,
            error_code=code,
            error_message=str(exc),
            requested_at=requested_at,
            received_at=received_at,
            latency_ms=latency_ms,
            attempt_count=attempt_count,
            circuit_open=circuit_open or code == "CIRCUIT_OPEN",
        )
        result = CollectionResult.degraded(
            [],
            error=f"{provider} degraded: {code}",
            as_of=as_of,
            freshness_class=freshness_class,
        )
        return result, diagnostics

    diagnostics = ProviderDiagnostics.unavailable(
        provider=provider,
        error_code=code,
        error_message=str(exc),
        requested_at=requested_at,
        received_at=received_at,
        latency_ms=latency_ms,
        attempt_count=attempt_count,
        circuit_open=circuit_open,
    )
    result = CollectionResult.unavailable(
        error=f"{provider} unavailable: {code}",
        as_of=as_of,
        freshness_class=freshness_class,
    )
    return result, diagnostics


def assert_not_no_event_on_failure(status: CollectionStatus) -> None:
    if status is CollectionStatus.NO_EVENT:
        raise AssertionError("provider failure must not be reported as NO_EVENT")
