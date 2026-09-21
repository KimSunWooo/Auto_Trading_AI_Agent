"""Map MarketContext onto long/short feature views. Missing values stay None."""

from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.agent_views import (
    EntrySnapshot,
    LongTermFeatures,
    ShortTermFeatures,
)
from ai_investment_agent.domain.context import MarketContext
from ai_investment_agent.domain.enums import EventDirection


def long_features_from(
    context: MarketContext, *, last_price: Decimal | None = None
) -> LongTermFeatures:
    quant = context.quantitative
    events = context.event_features
    return LongTermFeatures(
        daily_trend=quant.trend,
        weekly_trend=quant.weekly_trend,
        ma20=quant.ma20,
        ma60=quant.ma60,
        ma120=quant.ma120,
        last_price=last_price,
        momentum=quant.momentum,
        drawdown=quant.drawdown,
        volatility=quant.volatility,
        sector_strength=None,
        macro_risk=_decimal(events.macro_risk),
        long_horizon_event_bias=_signed_bias(events.dominant_direction, events.effective_impact),
    )


def short_features_from(
    context: MarketContext, *, last_price: Decimal | None = None
) -> ShortTermFeatures:
    quant = context.quantitative
    events = context.event_features
    return ShortTermFeatures(
        momentum=quant.momentum,
        volatility=quant.volatility,
        liquidity=quant.liquidity,
        last_price=last_price,
        short_lived_event_bias=_signed_bias(events.dominant_direction, events.effective_impact),
        volume_spike=quant.volume_ratio,
    )


def entry_from(context: MarketContext) -> EntrySnapshot | None:
    priced = context.priced_in
    if priced is None:
        return None
    return EntrySnapshot(
        already_priced_in=priced.already_priced_in,
        remaining_edge=priced.remaining_edge,
        liquidity=float(context.quantitative.liquidity) if context.quantitative.liquidity is not None else None,
    )


def _signed_bias(direction: EventDirection, impact: float) -> Decimal:
    if direction is EventDirection.NEGATIVE:
        return Decimal(str(-impact))
    if direction is EventDirection.POSITIVE:
        return Decimal(str(impact))
    return Decimal(0)


def _decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
