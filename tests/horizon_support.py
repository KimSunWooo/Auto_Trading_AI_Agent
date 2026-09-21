from datetime import datetime, timezone
from decimal import Decimal

from ai_investment_agent.adapters.in_memory import (
    InMemoryDecisionPublisher,
    InMemoryDecisionRepository,
)
from ai_investment_agent.agents.investment_agent import (
    InvestmentJudgmentAgent,
    InvestmentJudgmentRequest,
)
from ai_investment_agent.domain.agent_views import (
    EntrySnapshot,
    LongTermFeatures,
    ShortTermFeatures,
)
from ai_investment_agent.domain.enums import MarketRegimeType
from ai_investment_agent.domain.market import MarketRegime, MarketSnapshot
from tests.support import provided_capital
from tests.context_support import rising_series

AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def make_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        ticker="005930",
        as_of=AS_OF,
        last_price=Decimal("71000"),
        data_completeness=Decimal("0.95"),
        volatility=Decimal("0.02"),
        liquidity_score=Decimal("0.8"),
    )


def make_regime(kind: MarketRegimeType = MarketRegimeType.SIDEWAYS) -> MarketRegime:
    return MarketRegime(
        regime=kind,
        confidence=0.0 if kind is MarketRegimeType.UNKNOWN else 0.6,
        as_of=AS_OF,
        explanation="UNKNOWN is not safe" if kind is MarketRegimeType.UNKNOWN else "fixture regime",
        detected_from="fixture",
    )


def bullish_long() -> LongTermFeatures:
    return LongTermFeatures(
        daily_trend=Decimal("0.80"),
        weekly_trend=Decimal("0.60"),
        ma20=Decimal("100"),
        ma60=Decimal("95"),
        ma120=Decimal("90"),
        last_price=Decimal("110"),
        momentum=Decimal("0.20"),
        drawdown=Decimal("0.03"),
        fundamentals_score=Decimal("0.70"),
        valuation_score=Decimal("0.60"),
        sector_strength=Decimal("0.50"),
        macro_risk=Decimal("0.10"),
        long_horizon_event_bias=Decimal("0.20"),
        volatility=Decimal("0.02"),
    )


def weak_long() -> LongTermFeatures:
    return LongTermFeatures()


def high_cost_long() -> LongTermFeatures:
    return LongTermFeatures(
        daily_trend=Decimal("0.80"),
        weekly_trend=Decimal("0.60"),
        ma20=Decimal("100"),
        ma60=Decimal("95"),
        last_price=Decimal("110"),
        momentum=Decimal("0.20"),
        drawdown=Decimal("0.40"),
        volatility=Decimal("0.30"),
        macro_risk=Decimal("0.20"),
    )


def bearish_short() -> ShortTermFeatures:
    return ShortTermFeatures(
        intraday_trend=Decimal("-0.85"),
        momentum=Decimal("-0.50"),
        volume_spike=Decimal("2.4"),
        short_lived_event_bias=Decimal("-0.70"),
        volatility=Decimal("0.04"),
        liquidity=Decimal("0.70"),
        last_price=Decimal("110"),
    )


def bullish_short() -> ShortTermFeatures:
    bars = rising_series(n=8)
    return ShortTermFeatures(
        intraday_trend=Decimal("1.00"),
        ohlcv_1m=bars,
        ohlcv_5m=bars,
        ohlcv_15m=bars,
        vwap=Decimal("100"),
        volume_spike=Decimal("2.4"),
        momentum=Decimal("0.50"),
        breakout=Decimal("1.00"),
        short_lived_event_bias=Decimal("1.00"),
        volatility=Decimal("0.005"),
        liquidity=Decimal("0.90"),
        spread=Decimal("0.10"),
        last_price=Decimal("110"),
    )


def weak_short() -> ShortTermFeatures:
    return ShortTermFeatures()


def good_entry() -> EntrySnapshot:
    return EntrySnapshot(
        extension_vs_ma=Decimal("0.01"),
        already_priced_in=0.20,
        remaining_edge=0.60,
        liquidity=Decimal("0.80"),
    )


def poor_entry() -> EntrySnapshot:
    return EntrySnapshot(
        extension_vs_ma=Decimal("0.08"),
        already_priced_in=0.92,
        remaining_edge=0.08,
        vwap_distance=Decimal("0.05"),
    )


def make_investment_agent() -> tuple[InvestmentJudgmentAgent, InMemoryDecisionRepository]:
    repository = InMemoryDecisionRepository()
    publisher = InMemoryDecisionPublisher()
    agent = InvestmentJudgmentAgent(
        repository=repository,
        publisher=publisher,
        now_fn=lambda: AS_OF,
    )
    return agent, repository


def judge(
    *,
    long_features: LongTermFeatures,
    short_features: ShortTermFeatures,
    regime: MarketRegimeType = MarketRegimeType.SIDEWAYS,
    entry: EntrySnapshot | None = None,
    **kwargs,
):
    agent, _ = make_investment_agent()
    return agent.judge(
        InvestmentJudgmentRequest(
            ticker="005930",
            snapshot=make_snapshot(),
            regime=make_regime(regime),
            long_features=long_features,
            short_features=short_features,
            capital_context=kwargs.pop("capital_context", provided_capital()),
            entry=entry,
            **kwargs,
        )
    )
