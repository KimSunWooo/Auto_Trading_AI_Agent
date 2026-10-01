"""Component and overall health. UNKNOWN is never treated as HEALTHY.

GET /health and GET /providers/health are observation-only. They read the
last process snapshot and never call collector.collect or the LLM.
That last snapshot is not a specific decisionId.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from ai_investment_agent.adapters.live.diagnostics import ProviderDiagnostics
from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, DataMode, ModelHealthStatus
from ai_investment_agent.domain.evaluation import ModelHealthMetrics
from ai_investment_agent.domain.runtime import ProviderStatus

# Display-only. Does not change collection freshness or decision gates.
OBSERVATION_STALE_AFTER_SECONDS = 900.0


class ComponentHealth(DomainModel):
    name: str
    status: ModelHealthStatus
    detail: str = ""
    last_observed_at: datetime | None = None
    observation_age_seconds: float | None = None
    observation_stale: bool = False
    observation_source: str = "unobserved"


class ServiceHealthReport(DomainModel):
    status: ModelHealthStatus
    market_data_health: ComponentHealth
    external_data_health: ComponentHealth
    disclosure_health: ComponentHealth | None = None
    macro_health: ComponentHealth | None = None
    news_health: ComponentHealth | None = None
    scheduled_health: ComponentHealth | None = None
    llm_health: ComponentHealth | None = None
    model_health: ComponentHealth
    database_health: ComponentHealth
    persistence_health: ComponentHealth | None = None
    event_pipeline_health: ComponentHealth
    unknown_treated_as_healthy: Literal[False] = False
    orders_enabled: Literal[False] = False
    broker_connected: Literal[False] = False
    auto_trading_system_connected: Literal[False] = False
    runtime_profile: str = DataMode.FIXTURE.value
    data_mode: str = DataMode.FIXTURE.value
    terminal_artifact: str = "TradeProposal"
    mode: str = "judgment_only"
    components: list[ComponentHealth] = Field(default_factory=list)
    observation_only: Literal[True] = True
    probes_on_read: Literal[False] = False
    scoped_to_decision_id: None = None

    @property
    def treated_as_healthy(self) -> bool:
        return self.status is ModelHealthStatus.HEALTHY


def collect_health(service: AnalysisService) -> ServiceHealthReport:
    """Process-level last observation. Does not collect or open sockets."""
    now = service._now()
    market_component = _market_health(service, now)
    news_component = _provider_component(
        service,
        now,
        name="NewsHealth",
        collector=service.news,
        diagnostics_key="news",
        readiness_name="news",
        fallback="news",
    )
    disclosure_component = _provider_component(
        service,
        now,
        name="DisclosureHealth",
        collector=service.disclosure,
        diagnostics_key="disclosure",
        readiness_name="disclosure",
        fallback="disclosure",
    )
    macro_component = _provider_component(
        service,
        now,
        name="MacroHealth",
        collector=service.macro,
        diagnostics_key="macro",
        readiness_name="macro",
        fallback="macro",
    )
    scheduled_component = _scheduled_health(service, now)
    external_component = _external_health(service, now)
    llm_component = _llm_health(service, now)
    metrics = service.model_health.assess(service.repository.list_snapshots())
    model_component = ComponentHealth(
        name="ModelHealth",
        status=metrics.status,
        detail=_model_detail(metrics),
        observation_source="in_process",
    )
    database_component = ComponentHealth(
        name="DatabaseHealth",
        status=ModelHealthStatus.HEALTHY,
        detail="in-memory decision journal is reachable; not a broker database",
        observation_source="in_process",
    )
    persistence_component = ComponentHealth(
        name="PersistenceHealth",
        status=ModelHealthStatus.HEALTHY,
        detail=(
            "InMemory persistence OK for LIVE_OBSERVATION smoke; "
            "durable store required before long-running LIVE_SHADOW soak"
        ),
        observation_source="in_process",
    )
    pipeline_component = _pipeline_health(service)
    components = [
        market_component,
        disclosure_component,
        macro_component,
        news_component,
        scheduled_component,
        llm_component,
        external_component,
        model_component,
        database_component,
        persistence_component,
        pipeline_component,
    ]
    return ServiceHealthReport(
        status=aggregate_status([item.status for item in components]),
        market_data_health=market_component,
        external_data_health=external_component,
        disclosure_health=disclosure_component,
        macro_health=macro_component,
        news_health=news_component,
        scheduled_health=scheduled_component,
        llm_health=llm_component,
        model_health=model_component,
        database_health=database_component,
        persistence_health=persistence_component,
        event_pipeline_health=pipeline_component,
        components=components,
        runtime_profile=service.runtime.data_mode.value,
        data_mode=service.runtime.data_mode.value,
    )


def provider_health_payload(service: AnalysisService) -> dict[str, Any]:
    """Secrets-free provider diagnostics for GET /providers/health."""
    report = collect_health(service)
    providers = []
    for component in (
        report.market_data_health,
        report.disclosure_health,
        report.macro_health,
        report.news_health,
        report.scheduled_health,
        report.llm_health,
        report.event_pipeline_health,
        report.model_health,
        report.persistence_health,
    ):
        if component is None:
            continue
        providers.append(
            {
                "name": component.name,
                "status": component.status.value,
                "detail": component.detail,
                "lastObservedAt": (
                    component.last_observed_at.isoformat()
                    if component.last_observed_at is not None
                    else None
                ),
                "observationStale": component.observation_stale,
                "observationSource": component.observation_source,
            }
        )
    return {
        "providers": providers,
        "unknownIsHealthy": False,
        "ordersEnabled": False,
        "brokerConnected": False,
        "autoTradingSystemConnected": False,
        "dataMode": service.runtime.data_mode.value,
        "observationOnly": True,
        "probesOnRead": False,
        "scopedToDecisionId": None,
    }


def aggregate_status(statuses: list[ModelHealthStatus]) -> ModelHealthStatus:
    if not statuses:
        return ModelHealthStatus.UNKNOWN
    if ModelHealthStatus.UNHEALTHY in statuses:
        return ModelHealthStatus.UNHEALTHY
    if ModelHealthStatus.DEGRADED in statuses:
        return ModelHealthStatus.DEGRADED
    if ModelHealthStatus.UNKNOWN in statuses:
        return ModelHealthStatus.UNKNOWN
    if all(status is ModelHealthStatus.HEALTHY for status in statuses):
        return ModelHealthStatus.HEALTHY
    return ModelHealthStatus.UNKNOWN


def _from_collection(status: CollectionStatus) -> ModelHealthStatus:
    if status is CollectionStatus.OK or status is CollectionStatus.NO_EVENT:
        return ModelHealthStatus.HEALTHY
    if status is CollectionStatus.STALE or status is CollectionStatus.DEGRADED:
        return ModelHealthStatus.DEGRADED
    if status is CollectionStatus.DATA_UNAVAILABLE:
        return ModelHealthStatus.UNHEALTHY
    return ModelHealthStatus.UNKNOWN


def _collection_detail(status: CollectionStatus, suffix: str) -> str:
    return f"{status.value}; {suffix}"


def _model_detail(metrics: ModelHealthMetrics) -> str:
    if metrics.status is ModelHealthStatus.UNKNOWN:
        return (
            "UNKNOWN is not HEALTHY. "
            f"sampleSize={metrics.sample_size}, outcomeSampleSize={metrics.outcome_sample_size}"
        )
    return f"{metrics.status.value}; sampleSize={metrics.sample_size}"


def _provider_label(collector: object, fallback: str) -> str:
    name = collector.__class__.__name__
    if name.startswith("Live"):
        return f"live adapter={name}"
    if name.startswith("Fixture"):
        return f"fixture collector={name}"
    return fallback


def _age_fields(observed_at: datetime | None, now: datetime) -> tuple[float | None, bool]:
    if observed_at is None:
        return None, False
    age = (now - observed_at).total_seconds()
    return age, age > OBSERVATION_STALE_AFTER_SECONDS


def _component(
    *,
    name: str,
    status: ModelHealthStatus,
    detail: str,
    now: datetime,
    observed_at: datetime | None,
    source: str,
) -> ComponentHealth:
    age, stale = _age_fields(observed_at, now)
    extra = ""
    if source == "unobserved":
        extra = "; not observed in this process; UNKNOWN is not HEALTHY"
    elif source == "not_configured":
        extra = ""
    elif stale:
        extra = f"; observation aged ({int(age)}s) — status is last observation, not a new probe"
    else:
        extra = "; process last observation, not a decisionId"
    return ComponentHealth(
        name=name,
        status=status,
        detail=detail + extra,
        last_observed_at=observed_at,
        observation_age_seconds=age,
        observation_stale=stale,
        observation_source=source,
    )


def _diagnostics(service: AnalysisService, collector: object, key: str) -> ProviderDiagnostics | None:
    direct = getattr(collector, "last_diagnostics", None)
    if isinstance(direct, ProviderDiagnostics):
        return direct
    captured = getattr(service, "provider_diagnostics", {}) or {}
    value = captured.get(key)
    if isinstance(value, ProviderDiagnostics):
        return value
    return None


def _captured_status(service: AnalysisService, key: str) -> CollectionStatus | None:
    captured = getattr(service, "provider_diagnostics", {}) or {}
    value = captured.get(key)
    if isinstance(value, ProviderDiagnostics):
        return value.status
    if isinstance(value, dict):
        raw = value.get("status")
        if raw in CollectionStatus._value2member_map_:
            return CollectionStatus(raw)
    return None


def _readiness_row(service: AnalysisService, name: str) -> ProviderStatus | None:
    readiness = service.last_readiness
    if readiness is None:
        return None
    for row in readiness.providers:
        if row.name == name:
            return row
    return None


def _observed_status(
    *,
    result: CollectionResult | None,
    diagnostics: ProviderDiagnostics | None,
    captured: CollectionStatus | None,
    readiness: ProviderStatus | None,
) -> tuple[CollectionStatus | None, datetime | None, str]:
    if result is not None:
        return result.status, result.as_of, "process_last"
    if diagnostics is not None:
        return diagnostics.status, diagnostics.received_at, "process_last"
    if captured is not None:
        return captured, None, "process_last"
    if readiness is not None:
        return readiness.status, None, "process_last"
    return None, None, "unobserved"


def _market_health(service: AnalysisService, now: datetime) -> ComponentHealth:
    status, observed_at, source = _observed_status(
        result=service.last_market,
        diagnostics=_diagnostics(service, service.market, "market"),
        captured=_captured_status(service, "market"),
        readiness=None,
    )
    label = _provider_label(service.market, "market")
    if status is None:
        return _component(
            name="MarketDataHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail="unobserved; " + label,
            now=now,
            observed_at=None,
            source="unobserved",
        )
    return _component(
        name="MarketDataHealth",
        status=_from_collection(status),
        detail=_collection_detail(status, label),
        now=now,
        observed_at=observed_at,
        source=source,
    )


def _provider_component(
    service: AnalysisService,
    now: datetime,
    *,
    name: str,
    collector: object,
    diagnostics_key: str,
    readiness_name: str,
    fallback: str,
) -> ComponentHealth:
    status, observed_at, source = _observed_status(
        result=None,
        diagnostics=_diagnostics(service, collector, diagnostics_key),
        captured=_captured_status(service, diagnostics_key),
        readiness=_readiness_row(service, readiness_name),
    )
    label = _provider_label(collector, fallback)
    if status is None:
        return _component(
            name=name,
            status=ModelHealthStatus.UNKNOWN,
            detail="unobserved; " + label,
            now=now,
            observed_at=None,
            source="unobserved",
        )
    return _component(
        name=name,
        status=_from_collection(status),
        detail=_collection_detail(status, label),
        now=now,
        observed_at=observed_at,
        source=source,
    )


def _external_health(service: AnalysisService, now: datetime) -> ComponentHealth:
    external = service.last_external
    if external is None:
        return _component(
            name="ExternalDataHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail="unobserved; aggregated news/disclosure/macro",
            now=now,
            observed_at=None,
            source="unobserved",
        )
    return _component(
        name="ExternalDataHealth",
        status=_from_collection(external.status),
        detail=_collection_detail(external.status, "aggregated news/disclosure/macro"),
        now=now,
        observed_at=external.as_of,
        source="process_last",
    )


def _scheduled_health(service: AnalysisService, now: datetime) -> ComponentHealth:
    name = service.scheduled.__class__.__name__
    if name.startswith("Unconfigured"):
        return _component(
            name="ScheduledHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail=(
                "NOT_CONFIGURED; optional live calendar; "
                f"collector={name}; not NO_EVENT"
            ),
            now=now,
            observed_at=None,
            source="not_configured",
        )
    status, observed_at, source = _observed_status(
        result=None,
        diagnostics=_diagnostics(service, service.scheduled, "scheduled"),
        captured=_captured_status(service, "scheduled"),
        readiness=_readiness_row(service, "scheduledEvent"),
    )
    if status is None:
        return _component(
            name="ScheduledHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail="unobserved; " + _provider_label(service.scheduled, "scheduled"),
            now=now,
            observed_at=None,
            source="unobserved",
        )
    error = ""
    row = _readiness_row(service, "scheduledEvent")
    if row is not None and row.error:
        error = row.error
    if "NOT_CONFIGURED" in error:
        return _component(
            name="ScheduledHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail=(
                "NOT_CONFIGURED; optional live calendar; "
                f"collector={name}; not NO_EVENT"
            ),
            now=now,
            observed_at=observed_at,
            source="not_configured",
        )
    return _component(
        name="ScheduledHealth",
        status=_from_collection(status),
        detail=_collection_detail(status, _provider_label(service.scheduled, "scheduled")),
        now=now,
        observed_at=observed_at,
        source=source,
    )


def _llm_health(service: AnalysisService, now: datetime) -> ComponentHealth:
    llm = getattr(service, "llm", None)
    if llm is None:
        return _component(
            name="LlmHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail="LLM provider not attached; UNKNOWN is not HEALTHY",
            now=now,
            observed_at=None,
            source="unobserved",
        )
    diagnostics = getattr(llm, "last_diagnostics", None)
    if not isinstance(diagnostics, ProviderDiagnostics):
        return _component(
            name="LlmHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail=f"attached={llm.__class__.__name__}; no call yet",
            now=now,
            observed_at=None,
            source="unobserved",
        )
    return _component(
        name="LlmHealth",
        status=_from_collection(diagnostics.status),
        detail=_collection_detail(diagnostics.status, llm.__class__.__name__),
        now=now,
        observed_at=diagnostics.received_at,
        source="process_last",
    )


def _pipeline_health(service: AnalysisService) -> ComponentHealth:
    if service.last_pipeline_error:
        return ComponentHealth(
            name="EventPipelineHealth",
            status=ModelHealthStatus.UNHEALTHY,
            detail=service.last_pipeline_error,
            observation_source="process_last",
        )
    if service.last_market is None:
        return ComponentHealth(
            name="EventPipelineHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail="event pipeline has not run in this process yet",
            observation_source="unobserved",
        )
    return ComponentHealth(
        name="EventPipelineHealth",
        status=ModelHealthStatus.HEALTHY,
        detail=(
            "event intelligence pipeline last run succeeded; "
            "process last evaluate, not a request-scoped decisionId"
        ),
        observation_source="process_last",
    )
