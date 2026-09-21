"""Runtime / data-mode settings. Live is never inferred from a missing profile."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import CollectionStatus, DataMode, DecisionReadinessStatus


class RuntimeSettings(DomainModel):
    data_mode: DataMode = DataMode.FIXTURE

    @property
    def allows_fixture_fallback(self) -> bool:
        return self.data_mode is DataMode.FIXTURE

    @property
    def is_live_compatible(self) -> bool:
        return self.data_mode in {DataMode.LIVE_OBSERVATION, DataMode.LIVE_SHADOW}

    @property
    def is_replay(self) -> bool:
        return self.data_mode is DataMode.REPLAY


class ProviderStatus(DomainModel):
    name: str
    status: CollectionStatus
    error: str | None = None


class DecisionReadiness(DomainModel):
    """Gate evaluated before a TradeProposal is allowed to recommend BUY."""

    status: DecisionReadinessStatus
    market_status: CollectionStatus
    providers: list[ProviderStatus]
    reason_codes: list[str]
    allows_new_buy: bool
    data_mode: DataMode = DataMode.FIXTURE

    @property
    def unknown_is_ready(self) -> bool:
        return False


class DecisionContextMetadata(DomainModel):
    """Judgment-artifact metadata. validUntil is not an order TTL."""

    analysis_as_of: datetime
    generated_at: datetime
    valid_until: datetime
    data_mode: DataMode = DataMode.FIXTURE
    context_fingerprint: str
    provider_health: list[ProviderStatus] = Field(default_factory=list)
    readiness_status: DecisionReadinessStatus = DecisionReadinessStatus.UNKNOWN


DEFAULT_RUNTIME = RuntimeSettings()
