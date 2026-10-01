"""Component and overall health. UNKNOWN is never treated as HEALTHY."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ai_investment_agent.analysis.service import AnalysisService
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.enums import CollectionStatus, DataMode, ModelHealthStatus
from ai_investment_agent.domain.evaluation import ModelHealthMetrics


class ComponentHealth(DomainModel):
    name: str
    status: ModelHealthStatus
    detail: str = ""


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

    @property
    def treated_as_healthy(self) -> bool:
        return self.status is ModelHealthStatus.HEALTHY


def collect_health(service: AnalysisService) -> ServiceHealthReport:
    as_of = service._now()
    market = service.last_market or service.market.collect("005930", as_of)
    news = service.news.collect("005930", as_of)
    disclosure = service.disclosure.collect("005930", as_of)
    macro = service.macro.collect(as_of)
    scheduled = service.scheduled.collect(as_of, ticker="005930")
    external = service.last_external
    if external is None:
        items = [*news.items, *disclosure.items, *macro.items]
        if items:
            external = CollectionResult.ok(items, as_of=as_of)
        else:
            external = CollectionResult.no_event(as_of=as_of)

    market_component = ComponentHealth(
        name="MarketDataHealth",
        status=_from_collection(market.status),
        detail=_collection_detail(
            market.status,
            _provider_label(service.market, "market"),
        ),
    )
    disclosure_component = ComponentHealth(
        name="DisclosureHealth",
        status=_from_collection(disclosure.status),
        detail=_collection_detail(disclosure.status, _provider_label(service.disclosure, "disclosure")),
    )
    macro_component = ComponentHealth(
        name="MacroHealth",
        status=_from_collection(macro.status),
        detail=_collection_detail(macro.status, _provider_label(service.macro, "macro")),
    )
    news_component = ComponentHealth(
        name="NewsHealth",
        status=_from_collection(news.status),
        detail=_collection_detail(news.status, _provider_label(service.news, "news")),
    )
    scheduled_component = _scheduled_health(service, scheduled)
    external_component = ComponentHealth(
        name="ExternalDataHealth",
        status=_from_collection(external.status),
        detail=_collection_detail(external.status, "aggregated news/disclosure/macro"),
    )
    llm_component = _llm_health(service)
    metrics = service.model_health.assess(service.repository.list_snapshots())
    model_component = ComponentHealth(
        name="ModelHealth",
        status=metrics.status,
        detail=_model_detail(metrics),
    )
    database_component = ComponentHealth(
        name="DatabaseHealth",
        status=ModelHealthStatus.HEALTHY,
        detail="in-memory decision journal is reachable; not a broker database",
    )
    persistence_component = ComponentHealth(
        name="PersistenceHealth",
        status=ModelHealthStatus.HEALTHY,
        detail=(
            "InMemory persistence OK for LIVE_OBSERVATION smoke; "
            "durable store required before long-running LIVE_SHADOW soak"
        ),
    )
    _ = service.repository.list_snapshots()
    if service.last_pipeline_error:
        pipeline_status = ModelHealthStatus.UNHEALTHY
        pipeline_detail = service.last_pipeline_error
    elif service.last_market is None:
        pipeline_status = ModelHealthStatus.UNKNOWN
        pipeline_detail = "event pipeline has not run in this process yet"
    else:
        pipeline_status = ModelHealthStatus.HEALTHY
        pipeline_detail = "event intelligence pipeline last run succeeded"
    pipeline_component = ComponentHealth(
        name="EventPipelineHealth",
        status=pipeline_status,
        detail=pipeline_detail,
    )
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
            }
        )
    return {
        "providers": providers,
        "unknownIsHealthy": False,
        "ordersEnabled": False,
        "brokerConnected": False,
        "autoTradingSystemConnected": False,
        "dataMode": service.runtime.data_mode.value,
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


def _scheduled_health(service: AnalysisService, scheduled: CollectionResult) -> ComponentHealth:
    name = service.scheduled.__class__.__name__
    error = scheduled.error or ""
    if "NOT_CONFIGURED" in error or name.startswith("Unconfigured"):
        return ComponentHealth(
            name="ScheduledHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail=(
                "NOT_CONFIGURED; optional live calendar; "
                f"collector={name}; not NO_EVENT"
            ),
        )
    return ComponentHealth(
        name="ScheduledHealth",
        status=_from_collection(scheduled.status),
        detail=_collection_detail(scheduled.status, _provider_label(service.scheduled, "scheduled")),
    )


def _llm_health(service: AnalysisService) -> ComponentHealth:
    llm = getattr(service, "llm", None)
    if llm is None:
        return ComponentHealth(
            name="LlmHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail="LLM provider not attached; UNKNOWN is not HEALTHY",
        )
    diagnostics = getattr(llm, "last_diagnostics", None)
    if diagnostics is None:
        return ComponentHealth(
            name="LlmHealth",
            status=ModelHealthStatus.UNKNOWN,
            detail=f"attached={llm.__class__.__name__}; no call yet",
        )
    status = diagnostics.status if hasattr(diagnostics, "status") else CollectionStatus.DATA_UNAVAILABLE
    return ComponentHealth(
        name="LlmHealth",
        status=_from_collection(status),
        detail=_collection_detail(status, llm.__class__.__name__),
    )
