"""Mutate the virtual AI sleeve. This is not a brokerage ledger."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ai_investment_agent.domain.enums import Horizon
from ai_investment_agent.domain.shadow import (
    ShadowFill,
    ShadowPortfolio,
    ShadowPosition,
)


def apply_buy(state: ShadowPortfolio, fill: ShadowFill, horizon: Horizon) -> ShadowPortfolio:
    cash = state.cash + fill.cash_delta
    positions = [item.model_copy() for item in state.positions]
    current = next((item for item in positions if item.ticker == fill.ticker), None)
    if current is None:
        positions.append(
            ShadowPosition(
                ticker=fill.ticker,
                quantity=fill.quantity,
                average_cost=fill.fill_price,
                market_price=fill.fill_price,
                market_value=fill.quantity * fill.fill_price,
                unrealized_pnl=Decimal(0),
                realized_pnl=Decimal(0),
                opened_at=fill.filled_at,
                horizon=horizon,
            )
        )
    else:
        total_qty = current.quantity + fill.quantity
        current.average_cost = (
            (current.average_cost * current.quantity) + (fill.fill_price * fill.quantity)
        ) / total_qty
        current.quantity = total_qty
        current.market_price = fill.fill_price
        current.market_value = current.quantity * fill.fill_price
        current.unrealized_pnl = (fill.fill_price - current.average_cost) * current.quantity
    return _revalue(state, positions, cash, fill.filled_at)


def apply_sell(state: ShadowPortfolio, fill: ShadowFill) -> ShadowPortfolio:
    positions = [item.model_copy() for item in state.positions]
    current = next((item for item in positions if item.ticker == fill.ticker), None)
    if current is None:
        raise ValueError("no shadow position to sell")
    realized = (fill.fill_price - current.average_cost) * fill.quantity - fill.fee - fill.tax
    current.quantity = current.quantity - fill.quantity
    current.realized_pnl = current.realized_pnl + realized
    if current.quantity == 0:
        positions = [item for item in positions if item.ticker != fill.ticker]
    else:
        current.market_value = current.quantity * (current.market_price or fill.fill_price)
        current.unrealized_pnl = (
            (current.market_price or fill.fill_price) - current.average_cost
        ) * current.quantity
    cash = state.cash + fill.cash_delta
    updated = _revalue(state, positions, cash, fill.filled_at)
    return updated.model_copy(
        update={"realized_pnl": state.realized_pnl + realized}
    )


def mark_positions(
    state: ShadowPortfolio,
    prices: dict[str, Decimal],
    at: datetime,
) -> ShadowPortfolio:
    positions: list[ShadowPosition] = []
    unrealized = Decimal(0)
    for item in state.positions:
        price = prices.get(item.ticker, item.market_price or item.average_cost)
        market_value = item.quantity * price
        upnl = (price - item.average_cost) * item.quantity
        unrealized += upnl
        positions.append(
            item.model_copy(
                update={
                    "market_price": price,
                    "market_value": market_value,
                    "unrealized_pnl": upnl,
                }
            )
        )
    return _revalue(state, positions, state.cash, at, unrealized=unrealized)


def _revalue(
    state: ShadowPortfolio,
    positions: list[ShadowPosition],
    cash: Decimal,
    at: datetime,
    unrealized: Decimal | None = None,
) -> ShadowPortfolio:
    _ = at
    if unrealized is None:
        unrealized = sum((item.unrealized_pnl for item in positions), Decimal(0))
    equity = cash + sum((item.market_value for item in positions), Decimal(0))
    peak = state.peak_equity if state.peak_equity >= equity else equity
    drawdown = Decimal(0) if peak <= 0 else (peak - equity) / peak
    return state.model_copy(
        update={
            "cash": cash,
            "positions": positions,
            "unrealized_pnl": unrealized,
            "equity": equity,
            "peak_equity": peak,
            "drawdown": drawdown,
        }
    )
