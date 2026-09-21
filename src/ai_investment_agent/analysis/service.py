"""End-to-end analysis pipeline. Stops at TradeProposal. Never places orders."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from ai_investment_agent.adapters.event_store import InMemoryIntelligenceEventStore
from ai_investment_agent.adapters.fixtures.embeddings import HashedBagEmbeddingProvider
from ai_investment_agent.adapters.fixtures.portfolio import fixture_capital
from ai_investment_agent.adapters.in_memory import (
    InMemoryDecisionPublisher,
    InMemoryDecisionRepository,
)
from ai_investment_agent.agents.investment_agent import (
    InvestmentJudgmentAgent,
    InvestmentJudgmentRequest,
)
from ai_investment_agent.analysis.features import (
    entry_from,
    long_features_from,
    short_features_from,
)
from ai_investment_agent.collectors.intelligence import (
    FixtureDisclosureCollector,
    FixtureMacroCollector,
    FixtureNewsCollector,
    FixtureScheduledEventCollector,
)
from ai_investment_agent.collectors.market import FixtureMarketDataCollector
from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.collection import CollectionResult
from ai_investment_agent.domain.context import PriceSeries
from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.enums import (
    Action,
    CollectionStatus,
    EventSeverity,
    MarketDataKind,
)
from ai_investment_agent.domain.event_intelligence import AnalyzedMarketEvent, RawEvent
from ai_investment_agent.domain.external_intelligence import IntelligenceRecord
from ai_investment_agent.domain.journal import DecisionRecord
from ai_investment_agent.domain.market import MarketEvent, MarketSnapshot
from ai_investment_agent.domain.market_feed import MarketDataRecord
from ai_investment_agent.domain.shadow import ShadowExecutionResult
from ai_investment_agent.evaluation.health import ModelHealthAssessor
from ai_investment_agent.evaluation.quality import QualityEvaluator
from ai_investment_agent.features.engine import MarketContextEngine
from ai_investment_agent.intelligence.pipeline import EventIntelligenceEngine
from ai_investment_agent.replay.service import ReplayBundle, ReplayService
from ai_investment_agent.shadow.service import ShadowTradingService

FIXTURE_AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)

PIPELINE_STAGES = (
    "MARKET_DATA",
    "EXTERNAL_EVENT_DATA",
    "NORMALIZATION",
    "EVENT_INTELLIGENCE",
    "MARKET_CONTEXT",
    "FEATURE_ENGINE",
    "LONG_SHORT_ANALYSIS",
    "HORIZON_SELECTION",
    "CAPITAL_POLICY_ASSESSMENT",
    "TRADE_PROPOSAL",
    "DECISION_JOURNAL",
    "REPLAY_READY",
    "SHADOW_EXECUTION",
)


class AnalysisResult(DomainModel):
    decision_id: str
    ticker: str
    action: Action
    proposal_horizon: str
    snapshot: DecisionSnapshot
    record: DecisionRecord
    pipeline: list[str] = Field(default_factory=list)
    market_status: CollectionStatus
    external_status: CollectionStatus
    analyzed_event_count: int = 0
    orders_placed: Literal[0] = 0
    broker_called: Literal[False] = False
    shadow_execution: ShadowExecutionResult | None = None


class AnalysisService:
    """Fixture-backed judgment service. Auto-Trading-system is not connected."""

    def __init__(
        self,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now_fn or (lambda: FIXTURE_AS_OF)
        self.repository = InMemoryDecisionRepository()
        self.publisher = InMemoryDecisionPublisher()
        self.event_store = InMemoryIntelligenceEventStore()
        self.market = FixtureMarketDataCollector.from_file()
        self.news = FixtureNewsCollector.from_file()
        self.disclosure = FixtureDisclosureCollector.from_file()
        self.macro = FixtureMacroCollector.from_file()
        self.scheduled = FixtureScheduledEventCollector.from_file()
        self.intelligence = EventIntelligenceEngine(
            self.event_store,
            embeddings=HashedBagEmbeddingProvider(),
            now_fn=self._now,
        )
        self.features = MarketContextEngine()
        self.agent = InvestmentJudgmentAgent(
            repository=self.repository,
            publisher=self.publisher,
            now_fn=self._now,
        )
        self.replay = ReplayService(self.repository)
        self.model_health = ModelHealthAssessor()
        self.quality = QualityEvaluator()
        self.shadow = ShadowTradingService()
        self.last_market: CollectionResult[MarketDataRecord] | None = None
        self.last_external: CollectionResult[IntelligenceRecord] | None = None
        self.last_pipeline_error: str | None = None

    def evaluate(
        self,
        ticker: str,
        *,
        as_of: datetime | None = None,
        capital_context: CapitalContext | None = None,
    ) -> AnalysisResult:
        moment = as_of or self._now()
        self.last_pipeline_error = None
        try:
            return self._evaluate(ticker, moment, capital_context)
        except Exception as exc:
            self.last_pipeline_error = str(exc)
            raise

    def _evaluate(
        self,
        ticker: str,
        as_of: datetime,
        capital_context: CapitalContext | None,
    ) -> AnalysisResult:
        market = self.market.collect(ticker, as_of)
        self.last_market = market
        news = self.news.collect(ticker, as_of)
        disclosure = self.disclosure.collect(ticker, as_of)
        macro = self.macro.collect(as_of)
        scheduled = self.scheduled.collect(as_of, ticker=ticker)
        external_items = [
            *news.items,
            *disclosure.items,
            *macro.items,
            *scheduled.items,
        ]
        external_status = _merge_external_status([news, disclosure, macro, scheduled])
        if external_status is CollectionStatus.OK:
            self.last_external = CollectionResult.ok(external_items, as_of=as_of)
        elif external_status is CollectionStatus.NO_EVENT:
            self.last_external = CollectionResult.no_event(as_of=as_of)
        elif external_status is CollectionStatus.STALE:
            self.last_external = CollectionResult.stale(external_items, as_of=as_of)
        else:
            self.last_external = CollectionResult.unavailable(
                error="external intelligence unavailable",
                as_of=as_of,
            )

        raw_events = [intelligence_to_raw(item) for item in external_items]
        analyzed = self.intelligence.ingest_many(raw_events) if raw_events else []
        series = price_series_from(market.items)
        snapshot = snapshot_from(ticker, as_of, market.items)
        context = self.features.build(
            ticker=ticker,
            as_of=as_of,
            series=series,
            events=analyzed,
            liquidity=_liquidity(market.items),
        )
        judgment_events = [analyzed_to_market_event(item, ticker) for item in analyzed]
        judged = self.agent.judge(
            InvestmentJudgmentRequest(
                ticker=ticker,
                snapshot=snapshot,
                regime=context.regime,
                long_features=long_features_from(context, last_price=snapshot.last_price),
                short_features=short_features_from(context, last_price=snapshot.last_price),
                capital_context=capital_context or fixture_capital(),
                entry=entry_from(context),
                feature_snapshot=context,
                events=tuple(judgment_events),
            )
        )
        shadow_result = self.shadow.apply_snapshot(judged)
        return AnalysisResult(
            decision_id=judged.decision_id,
            ticker=ticker,
            action=judged.proposal.action,
            proposal_horizon=judged.proposal.horizon.value,
            snapshot=judged,
            record=judged.to_record(),
            pipeline=list(PIPELINE_STAGES),
            market_status=market.status,
            external_status=external_status,
            analyzed_event_count=len(analyzed),
            orders_placed=0,
            broker_called=False,
            shadow_execution=shadow_result,
        )

    def list_decisions(self) -> list[DecisionRecord]:
        return [item.to_record() for item in self.repository.list_snapshots()]

    def get_decision(self, decision_id: str) -> DecisionSnapshot | None:
        return self.repository.get_snapshot(decision_id)

    def replay_decision(self, decision_id: str) -> ReplayBundle:
        return self.replay.replay(decision_id)


def intelligence_to_raw(record: IntelligenceRecord) -> RawEvent:
    return RawEvent(
        raw_id=record.record_id,
        source=record.source,
        source_id=record.record_id,
        headline=record.headline,
        body=record.body or "",
        published_at=record.timestamps.published_at,
        collected_at=record.timestamps.collected_at,
        language=record.language,
        kind=record.kind,
        country=record.country,
        ticker=record.ticker,
        is_untrusted=True,
    )


def analyzed_to_market_event(event: AnalyzedMarketEvent, ticker: str) -> MarketEvent:
    return MarketEvent(
        event_id=event.event_id,
        ticker=ticker,
        event_type=event.event_type,
        title=event.headline,
        occurred_at=event.analyzed_at,
        severity=EventSeverity.INFO,
        source="event-intelligence",
        payload={"clusterId": event.cluster_id, "direction": event.direction.value},
    )


def price_series_from(records: list[MarketDataRecord]) -> PriceSeries:
    points: list[tuple[datetime, Decimal, Decimal | None]] = []
    for record in records:
        if record.kind is MarketDataKind.OHLCV and record.ohlcv is not None:
            points.append((record.ohlcv.bar_end, record.ohlcv.close, record.ohlcv.volume))
        elif record.kind is MarketDataKind.CURRENT_PRICE and record.value is not None:
            occurred = record.timestamps.event_occurred_at or record.timestamps.tradable_at
            points.append((occurred, record.value, None))
    points.sort(key=lambda item: item[0])
    timestamps = [item[0] for item in points]
    closes = [item[1] for item in points]
    volumes = [item[2] for item in points if item[2] is not None]
    if len(volumes) != len(closes):
        volumes = []
    return PriceSeries(timestamps=timestamps, closes=closes, volumes=volumes)


def snapshot_from(ticker: str, as_of: datetime, records: list[MarketDataRecord]) -> MarketSnapshot:
    last_price = _latest_value(records, MarketDataKind.CURRENT_PRICE)
    if last_price is None:
        ohlcv = [item.ohlcv for item in records if item.ohlcv is not None]
        if ohlcv:
            last_price = ohlcv[-1].close
    volume = _latest_value(records, MarketDataKind.VOLUME)
    volatility = _latest_value(records, MarketDataKind.VOLATILITY)
    liquidity = _latest_value(records, MarketDataKind.LIQUIDITY)
    present = sum(
        1
        for value in (last_price, volume, volatility, liquidity)
        if value is not None
    )
    completeness = Decimal(0) if not records else Decimal(str(min(1.0, 0.4 + 0.15 * present)))
    if last_price is not None:
        completeness = max(completeness, Decimal("0.7"))
    return MarketSnapshot(
        ticker=ticker,
        as_of=as_of,
        last_price=last_price,
        volume=volume,
        volatility=volatility or Decimal("0.05"),
        liquidity_score=liquidity,
        data_completeness=completeness,
        source="fixture-collector",
    )


def _latest_value(records: list[MarketDataRecord], kind: MarketDataKind) -> Decimal | None:
    matched = [item for item in records if item.kind is kind and item.value is not None]
    if not matched:
        return None
    matched.sort(key=lambda item: item.timestamps.tradable_at)
    return matched[-1].value


def _liquidity(records: list[MarketDataRecord]) -> float | None:
    value = _latest_value(records, MarketDataKind.LIQUIDITY)
    if value is None:
        return None
    return float(value)


def _merge_external_status(results: list[CollectionResult]) -> CollectionStatus:
    statuses = [item.status for item in results]
    if any(item.items for item in results):
        if all(item.status is CollectionStatus.STALE for item in results if item.items):
            return CollectionStatus.STALE
        return CollectionStatus.OK
    if all(status is CollectionStatus.NO_EVENT for status in statuses):
        return CollectionStatus.NO_EVENT
    return CollectionStatus.DATA_UNAVAILABLE
