"""Shadow trading book. These models are not broker Order/Fill/Position.

There is no conversion method to a live order. convertibleToBroker is
always false and cannot be set true.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.enums import (
    Action,
    Horizon,
    MarketRegimeType,
    ShadowOrderStatus,
    ShadowSide,
)
from ai_investment_agent.domain.market import MarketSnapshot


class ShadowCostModel(DomainModel):
    """Conservative virtual costs. Missing market microstructure is not free."""

    default_spread_bps: Decimal = Field(default=Decimal("10"), ge=0)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0)
    fee_bps: Decimal = Field(default=Decimal("15"), ge=0)
    sell_tax_bps: Decimal = Field(default=Decimal("23"), ge=0)
    min_liquidity_to_fill: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    unknown_liquidity_score: Decimal = Field(default=Decimal("0.35"), ge=0, le=1)
    low_liquidity_extra_slippage_bps: Decimal = Field(default=Decimal("20"), ge=0)


class ShadowMarketQuote(DomainModel):
    """Quote used only by the shadow book. Fixture/historical, never a live KIS tick."""

    ticker: str = Field(min_length=1)
    mid: Decimal = Field(gt=0)
    as_of: datetime
    spread_bps: Decimal | None = Field(default=None, ge=0)
    liquidity_score: Decimal | None = Field(default=None, ge=0, le=1)
    source: Literal["fixture"] = "fixture"

    @classmethod
    def from_snapshot(cls, snapshot: MarketSnapshot) -> ShadowMarketQuote | None:
        if snapshot.last_price is None or snapshot.last_price <= 0:
            return None
        return cls(
            ticker=snapshot.ticker,
            mid=snapshot.last_price,
            as_of=snapshot.as_of,
            spread_bps=None,
            liquidity_score=snapshot.liquidity_score,
            source="fixture",
        )


class ShadowOrder(DomainModel):
    """Virtual intent derived from a TradeProposal. Not a broker order."""

    shadow_order_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    side: ShadowSide
    intended_notional: Decimal = Field(ge=0)
    submitted_at: datetime
    status: ShadowOrderStatus
    reason_codes: list[str] = Field(default_factory=list)
    convertible_to_broker: Literal[False] = False

    @model_validator(mode="after")
    def forbid_broker_conversion(self) -> ShadowOrder:
        if self.convertible_to_broker:
            raise ValueError("ShadowOrder cannot be convertible to a broker order")
        if not self.shadow_order_id.startswith("sho_"):
            raise ValueError("shadowOrderId must use the sho_ prefix, not a broker id")
        return self


class ShadowFill(DomainModel):
    """Virtual fill. Not a broker execution report."""

    shadow_fill_id: str = Field(min_length=1)
    shadow_order_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    side: ShadowSide
    quantity: Decimal = Field(gt=0)
    mid_price: Decimal = Field(gt=0)
    fill_price: Decimal = Field(gt=0)
    spread_bps_applied: Decimal = Field(ge=0)
    slippage_bps_applied: Decimal = Field(ge=0)
    fee: Decimal = Field(ge=0)
    tax: Decimal = Field(ge=0)
    notional: Decimal = Field(ge=0)
    cash_delta: Decimal
    filled_at: datetime
    liquidity_score: Decimal | None = None
    convertible_to_broker: Literal[False] = False

    @model_validator(mode="after")
    def fill_must_not_be_mid_and_not_broker(self) -> ShadowFill:
        if self.convertible_to_broker:
            raise ValueError("ShadowFill cannot be convertible to a broker fill")
        if not self.shadow_fill_id.startswith("shf_"):
            raise ValueError("shadowFillId must use the shf_ prefix")
        if self.fill_price == self.mid_price:
            raise ValueError("Shadow fill must apply friction; fillPrice cannot equal mid")
        if self.side is ShadowSide.BUY and self.fill_price <= self.mid_price:
            raise ValueError("Shadow BUY must fill above mid")
        if self.side is ShadowSide.SELL and self.fill_price >= self.mid_price:
            raise ValueError("Shadow SELL must fill below mid")
        return self


class ShadowPosition(DomainModel):
    """Virtual holding. Not a brokerage lot."""

    ticker: str = Field(min_length=1)
    quantity: Decimal
    average_cost: Decimal = Field(ge=0)
    market_price: Decimal | None = None
    market_value: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    opened_at: datetime
    horizon: Horizon | None = None
    convertible_to_broker: Literal[False] = False

    @model_validator(mode="after")
    def forbid_broker_conversion(self) -> ShadowPosition:
        if self.convertible_to_broker:
            raise ValueError("ShadowPosition cannot be convertible to a broker position")
        return self


class ShadowPortfolio(DomainModel):
    """AI-only virtual account. Cash starts at aiCapitalLimit, not totalCapital."""

    initial_capital: Decimal = Field(ge=0)
    ai_capital_limit: Decimal = Field(ge=0)
    cash: Decimal = Field(ge=0)
    positions: list[ShadowPosition] = Field(default_factory=list)
    realized_pnl: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)
    equity: Decimal = Field(ge=0)
    peak_equity: Decimal = Field(ge=0)
    drawdown: Decimal = Field(ge=0)
    source: Literal["shadow_virtual"] = "shadow_virtual"
    convertible_to_broker: Literal[False] = False

    @classmethod
    def opened(cls, capital: CapitalContext) -> ShadowPortfolio:
        cash = capital.ai_capital_limit
        return cls(
            initial_capital=capital.total_capital,
            ai_capital_limit=capital.ai_capital_limit,
            cash=cash,
            positions=[],
            realized_pnl=Decimal(0),
            unrealized_pnl=Decimal(0),
            equity=cash,
            peak_equity=cash,
            drawdown=Decimal(0),
        )

    @model_validator(mode="after")
    def sleeve_and_broker_rules(self) -> ShadowPortfolio:
        if self.convertible_to_broker:
            raise ValueError("ShadowPortfolio cannot be convertible to a live account")
        return self

    @property
    def deployed_notional(self) -> Decimal:
        return sum((item.market_value for item in self.positions), Decimal("0"))


class ShadowSkipRecord(DomainModel):
    decision_id: str
    ticker: str
    action: Action
    mid: Decimal | None = None
    at: datetime
    regime: MarketRegimeType
    horizon: Horizon
    reason_codes: list[str] = Field(default_factory=list)


class ShadowExecutionResult(DomainModel):
    order: ShadowOrder
    fill: ShadowFill | None = None
    portfolio: ShadowPortfolio
    skipped: bool = False
    broker_called: Literal[False] = False
    live_order_placed: Literal[False] = False
