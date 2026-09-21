"""Conservative shadow fill pricing. Mid is never used as the fill."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from ai_investment_agent.domain.enums import ReasonCode, ShadowSide
from ai_investment_agent.domain.shadow import ShadowCostModel, ShadowMarketQuote

BPS = Decimal("10000")
PRICE_TICK = Decimal("1")


class ShadowCostBreakdown:
    def __init__(
        self,
        *,
        fill_price: Decimal,
        spread_bps: Decimal,
        slippage_bps: Decimal,
        reasons: list[str],
        liquidity: Decimal,
    ) -> None:
        self.fill_price = fill_price
        self.spread_bps = spread_bps
        self.slippage_bps = slippage_bps
        self.reasons = reasons
        self.liquidity = liquidity


def resolve_friction(
    quote: ShadowMarketQuote,
    side: ShadowSide,
    model: ShadowCostModel,
) -> tuple[ShadowCostBreakdown | None, list[str]]:
    reasons = [ReasonCode.SHADOW_COSTS_APPLIED.value, ReasonCode.SHADOW_FILL_NOT_MID.value]
    if quote.spread_bps is None:
        spread = model.default_spread_bps
        reasons.append(ReasonCode.SHADOW_CONSERVATIVE_SPREAD_DEFAULT.value)
    else:
        spread = quote.spread_bps

    if quote.liquidity_score is None:
        liquidity = model.unknown_liquidity_score
        reasons.append(ReasonCode.SHADOW_CONSERVATIVE_LIQUIDITY_DEFAULT.value)
    else:
        liquidity = quote.liquidity_score

    if liquidity < model.min_liquidity_to_fill:
        return None, [ReasonCode.SHADOW_REJECTED_LOW_LIQUIDITY.value]

    extra = Decimal(0)
    if liquidity < Decimal("0.50"):
        extra = model.low_liquidity_extra_slippage_bps * (
            (Decimal("0.50") - liquidity) / Decimal("0.30")
        )
    slip = model.slippage_bps + extra
    half_spread = spread / Decimal("2")
    total_bps = half_spread + slip
    if side is ShadowSide.BUY:
        raw = quote.mid * (BPS + total_bps) / BPS
        fill = raw.quantize(PRICE_TICK, rounding=ROUND_CEILING)
        if fill <= quote.mid:
            fill = quote.mid + PRICE_TICK
    else:
        raw = quote.mid * (BPS - total_bps) / BPS
        fill = raw.quantize(PRICE_TICK, rounding=ROUND_FLOOR)
        if fill >= quote.mid:
            fill = quote.mid - PRICE_TICK
        if fill <= 0:
            return None, [ReasonCode.SHADOW_REJECTED_NO_QUOTE.value]
    return (
        ShadowCostBreakdown(
            fill_price=fill,
            spread_bps=spread,
            slippage_bps=slip,
            reasons=reasons,
            liquidity=liquidity,
        ),
        reasons,
    )


def fee_on(notional: Decimal, model: ShadowCostModel) -> Decimal:
    return (notional * model.fee_bps / BPS).quantize(Decimal("1"), rounding=ROUND_CEILING)


def tax_on_sell(notional: Decimal, model: ShadowCostModel) -> Decimal:
    return (notional * model.sell_tax_bps / BPS).quantize(Decimal("1"), rounding=ROUND_CEILING)
