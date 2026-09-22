"""Provider diagnostics. Empty list is never success; status is mandatory."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import CollectionStatus


class ProviderDiagnostics(DomainModel):
    provider: str
    status: CollectionStatus
    requested_at: datetime | None = None
    received_at: datetime | None = None
    source_timestamp: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: float | None = None
    attempt_count: int = 0
    circuit_open: bool = False

    @classmethod
    def unavailable(
        cls,
        *,
        provider: str,
        error_code: str,
        error_message: str,
        requested_at: datetime | None = None,
        received_at: datetime | None = None,
        latency_ms: float | None = None,
        attempt_count: int = 0,
        circuit_open: bool = False,
    ) -> ProviderDiagnostics:
        return cls(
            provider=provider,
            status=CollectionStatus.DATA_UNAVAILABLE,
            requested_at=requested_at,
            received_at=received_at,
            error_code=error_code,
            error_message=error_message,
            latency_ms=latency_ms,
            attempt_count=attempt_count,
            circuit_open=circuit_open,
        )

    @classmethod
    def ok(
        cls,
        *,
        provider: str,
        requested_at: datetime | None = None,
        received_at: datetime | None = None,
        source_timestamp: datetime | None = None,
        latency_ms: float | None = None,
        attempt_count: int = 1,
    ) -> ProviderDiagnostics:
        return cls(
            provider=provider,
            status=CollectionStatus.OK,
            requested_at=requested_at,
            received_at=received_at,
            source_timestamp=source_timestamp,
            latency_ms=latency_ms,
            attempt_count=attempt_count,
        )

    @classmethod
    def no_event(
        cls,
        *,
        provider: str,
        requested_at: datetime | None = None,
        received_at: datetime | None = None,
        latency_ms: float | None = None,
        attempt_count: int = 1,
    ) -> ProviderDiagnostics:
        return cls(
            provider=provider,
            status=CollectionStatus.NO_EVENT,
            requested_at=requested_at,
            received_at=received_at,
            latency_ms=latency_ms,
            attempt_count=attempt_count,
        )

    @classmethod
    def degraded(
        cls,
        *,
        provider: str,
        error_code: str,
        error_message: str,
        requested_at: datetime | None = None,
        received_at: datetime | None = None,
        latency_ms: float | None = None,
        attempt_count: int = 0,
        circuit_open: bool = False,
    ) -> ProviderDiagnostics:
        return cls(
            provider=provider,
            status=CollectionStatus.DEGRADED,
            requested_at=requested_at,
            received_at=received_at,
            error_code=error_code,
            error_message=error_message,
            latency_ms=latency_ms,
            attempt_count=attempt_count,
            circuit_open=circuit_open,
        )


class ProviderHealthSnapshot(DomainModel):
    """Aggregated health for /providers/health. Secrets never included."""

    name: str
    status: CollectionStatus
    detail: str = ""
    last_diagnostics: ProviderDiagnostics | None = None
    configured: bool = False
