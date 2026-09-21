"""Component and overall health. UNKNOWN is never treated as HEALTHY."""

from __future__ import annotations

from typing import Literal

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
    model_health: ComponentHealth
    database_health: ComponentHealth
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
    external = service.last_external
    if external is None:
        news = service.news.collect("005930", as_of)
        disclosure = service.disclosure.collect("005930", as_of)
        items = [*news.items, *disclosure.items]
        if items:
            external = CollectionResult.ok(items, as_of=as_of)
        else:
            external = CollectionResult.no_event(as_of=as_of)

    market_component = ComponentHealth(
        name="MarketDataHealth",
        status=_from_collection(market.status),
        detail=_collection_detail(market.status, "fixture market collector; live quotes are not connected"),
    )
    external_component = ComponentHealth(
        name="ExternalDataHealth",
        status=_from_collection(external.status),
        detail=_collection_detail(
            external.status,
            "fixture news/disclosure collector; live wires are not connected",
        ),
    )
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
    _ = service.repository.list_snapshots()
    if service.last_pipeline_error:
        pipeline_status = ModelHealthStatus.UNHEALTHY
        pipeline_detail = service.last_pipeline_error
    elif service.last_market is None:
        pipeline_status = ModelHealthStatus.UNKNOWN
        pipeline_detail = "event pipeline has not run in this process yet"
    else:
        pipeline_status = ModelHealthStatus.HEALTHY
        pipeline_detail = "fixture event intelligence pipeline last run succeeded"
    pipeline_component = ComponentHealth(
        name="EventPipelineHealth",
        status=pipeline_status,
        detail=pipeline_detail,
    )
    components = [
        market_component,
        external_component,
        model_component,
        database_component,
        pipeline_component,
    ]
    return ServiceHealthReport(
        status=aggregate_status([item.status for item in components]),
        market_data_health=market_component,
        external_data_health=external_component,
        model_health=model_component,
        database_health=database_component,
        event_pipeline_health=pipeline_component,
        components=components,
        runtime_profile=service.runtime.data_mode.value,
        data_mode=service.runtime.data_mode.value,
    )


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
