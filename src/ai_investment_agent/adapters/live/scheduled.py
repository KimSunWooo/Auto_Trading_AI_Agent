"""Optional live scheduled-event collector. Missing calendar is not an empty calendar."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_investment_agent.adapters.live.diagnostics import ProviderDiagnostics
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord

PROVIDER = "scheduled"


class UnconfiguredScheduledEventCollector:
    """Optional live calendar stub.

    LIVE must not silently ingest fixture industry/corporate events.
    Absence of a live calendar provider is NOT_CONFIGURED / DATA_UNAVAILABLE,
    never a genuine empty calendar (NO_EVENT).
    """

    required = False

    def __init__(self) -> None:
        self.last_diagnostics: ProviderDiagnostics | None = None

    def collect(
        self,
        as_of: datetime,
        ticker: str | None = None,
    ) -> CollectionResult[IntelligenceRecord]:
        del ticker
        requested_at = datetime.now(timezone.utc)
        self.last_diagnostics = ProviderDiagnostics.unavailable(
            provider=PROVIDER,
            error_code="NOT_CONFIGURED",
            error_message="live scheduled calendar provider is not configured",
            requested_at=requested_at,
            received_at=requested_at,
        )
        return CollectionResult.unavailable(
            error="scheduledEvent NOT_CONFIGURED: live calendar provider is not configured",
            as_of=as_of,
            freshness_class=FreshnessClass.LONG_HORIZON,
        )


def is_unconfigured_scheduled(result: CollectionResult) -> bool:
    if result.status is not CollectionStatus.DATA_UNAVAILABLE:
        return False
    return "NOT_CONFIGURED" in (result.error or "")
