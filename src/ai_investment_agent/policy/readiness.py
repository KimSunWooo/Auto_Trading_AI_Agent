"""Decision readiness. Collection health is a gate, not a dashboard-only flag."""

from __future__ import annotations

from ai_investment_agent.collectors.scheduled import is_unconfigured_scheduled
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, DataMode, DecisionReadinessStatus, ReasonCode
from ai_investment_agent.domain.runtime import DecisionReadiness, ProviderStatus

# Market is always required. These external feeds gate new BUY.
REQUIRED_EXTERNAL_PROVIDERS = frozenset({"news", "disclosure", "macro"})
# Live calendar is optional. Missing config is NOT_CONFIGURED, not NO_EVENT,
# and does not by itself block a new BUY.
OPTIONAL_EXTERNAL_PROVIDERS = frozenset({"scheduledEvent"})


def assess_readiness(
    *,
    market: CollectionResult,
    providers: dict[str, CollectionResult],
    data_mode: DataMode = DataMode.FIXTURE,
) -> DecisionReadiness:
    reasons: list[str] = []
    provider_rows = [
        ProviderStatus(
            name=name,
            status=result.status,
            error=result.error,
            required=name not in OPTIONAL_EXTERNAL_PROVIDERS,
            error_code=_error_code(result),
        )
        for name, result in providers.items()
    ]

    if market.status is CollectionStatus.DATA_UNAVAILABLE:
        reasons.append(ReasonCode.MARKET_DATA_UNAVAILABLE.value)
        reasons.append(ReasonCode.DECISION_READINESS_BLOCKED.value)
        return DecisionReadiness(
            status=DecisionReadinessStatus.BLOCKED,
            market_status=market.status,
            providers=provider_rows,
            reason_codes=reasons,
            allows_new_buy=False,
            data_mode=data_mode,
        )
    if market.status is CollectionStatus.STALE:
        reasons.append(ReasonCode.MARKET_DATA_STALE.value)
        reasons.append(ReasonCode.DECISION_READINESS_BLOCKED.value)
        return DecisionReadiness(
            status=DecisionReadinessStatus.BLOCKED,
            market_status=market.status,
            providers=provider_rows,
            reason_codes=reasons,
            allows_new_buy=False,
            data_mode=data_mode,
        )

    blocking = [
        row
        for row in provider_rows
        if row.required
        and row.status
        in {CollectionStatus.DATA_UNAVAILABLE, CollectionStatus.STALE, CollectionStatus.DEGRADED}
    ]
    if blocking:
        reasons.append(ReasonCode.EXTERNAL_PROVIDER_DEGRADED.value)
        return DecisionReadiness(
            status=DecisionReadinessStatus.DEGRADED,
            market_status=market.status,
            providers=provider_rows,
            reason_codes=reasons,
            allows_new_buy=False,
            data_mode=data_mode,
        )

    return DecisionReadiness(
        status=DecisionReadinessStatus.READY,
        market_status=market.status,
        providers=provider_rows,
        reason_codes=reasons,
        allows_new_buy=True,
        data_mode=data_mode,
    )


def _error_code(result: CollectionResult) -> str | None:
    if is_unconfigured_scheduled(result):
        return "NOT_CONFIGURED"
    if result.status is CollectionStatus.DATA_UNAVAILABLE:
        return "DATA_UNAVAILABLE"
    if result.status is CollectionStatus.DEGRADED:
        return "DEGRADED"
    if result.status is CollectionStatus.STALE:
        return "STALE"
    return None
