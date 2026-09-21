"""Decision readiness. Collection health is a gate, not a dashboard-only flag."""

from __future__ import annotations

from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, DataMode, DecisionReadinessStatus, ReasonCode
from ai_investment_agent.domain.runtime import DecisionReadiness, ProviderStatus


def assess_readiness(
    *,
    market: CollectionResult,
    providers: dict[str, CollectionResult],
    data_mode: DataMode = DataMode.FIXTURE,
) -> DecisionReadiness:
    reasons: list[str] = []
    provider_rows = [
        ProviderStatus(name=name, status=result.status, error=result.error)
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

    statuses = [item.status for item in provider_rows]
    unavailable = sum(status is CollectionStatus.DATA_UNAVAILABLE for status in statuses)
    stale = sum(status is CollectionStatus.STALE for status in statuses)
    if unavailable or stale:
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
