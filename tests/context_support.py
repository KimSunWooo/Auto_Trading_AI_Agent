from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ai_investment_agent.domain.context import PriceSeries
from ai_investment_agent.domain.enums import (
    EventCategory,
    EventDirection,
    ImpactHorizon,
    SourceTier,
    VerificationStatus,
)
from ai_investment_agent.domain.event_intelligence import AnalyzedMarketEvent
from ai_investment_agent.domain.event_time import resolve_market_available_at
from ai_investment_agent.features.engine import MarketContextEngine

AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def rising_series(n: int = 12, start: float = 100.0, step: float = 0.4) -> PriceSeries:
    closes = [Decimal(str(start + i * step)) for i in range(n)]
    volumes = [Decimal("1000000") for _ in range(n)]
    timestamps = [AS_OF - timedelta(days=n - 1 - i) for i in range(n)]
    return PriceSeries(timestamps=timestamps, closes=closes, volumes=volumes)


def falling_series(n: int = 12) -> PriceSeries:
    closes = [Decimal(str(120 - i * 1.5)) for i in range(n)]
    volumes = [Decimal("2000000") for _ in range(n)]
    timestamps = [AS_OF - timedelta(days=n - 1 - i) for i in range(n)]
    return PriceSeries(timestamps=timestamps, closes=closes, volumes=volumes)


def analyzed_event(
    *,
    event_id: str = "evt_ctx_1",
    category: EventCategory = EventCategory.CORPORATE,
    direction: EventDirection = EventDirection.POSITIVE,
    magnitude: float = 0.8,
    source_trust: float = 0.9,
    novelty: float = 0.9,
    confidence: float = 0.85,
    horizon: ImpactHorizon = ImpactHorizon.DAYS,
    tickers: list[str] | None = None,
    analyzed_at: datetime | None = None,
    published_at: datetime | None = None,
    collected_at: datetime | None = None,
    market_available_at: datetime | None = None,
    headline: str = "Fixture event",
) -> AnalyzedMarketEvent:
    at = analyzed_at or AS_OF
    published = published_at if published_at is not None else at
    available = market_available_at or resolve_market_available_at(
        published_at=published,
        collected_at=collected_at,
    )
    return AnalyzedMarketEvent(
        event_id=event_id,
        cluster_id="ecl_ctx_1",
        event_type="EARNINGS" if category is EventCategory.CORPORATE else "CONFLICT",
        category=category,
        tickers=tickers or ["005930"],
        direction=direction,
        magnitude=magnitude,
        source_trust=source_trust,
        novelty=novelty,
        confidence=confidence,
        verification_status=VerificationStatus.VERIFIED,
        impact_horizon=horizon,
        headline=headline,
        article_count=1,
        source_ids=["src-1"],
        member_raw_ids=["raw-1"],
        source_tier=SourceTier.A,
        published_at=published,
        collected_at=collected_at,
        market_available_at=available,
        analyzed_at=at,
    )


def engine() -> MarketContextEngine:
    return MarketContextEngine()
