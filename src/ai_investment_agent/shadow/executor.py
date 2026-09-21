"""Apply TradeProposals to the shadow book. Never talks to a broker."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

from ai_investment_agent.domain.enums import (
    Action,
    ReasonCode,
    ShadowOrderStatus,
    ShadowSide,
)
from ai_investment_agent.domain.ids import new_shadow_fill_id, new_shadow_order_id
from ai_investment_agent.domain.proposal import TradeProposal
from ai_investment_agent.domain.shadow import (
    ShadowCostModel,
    ShadowExecutionResult,
    ShadowFill,
    ShadowMarketQuote,
    ShadowOrder,
    ShadowPortfolio,
    ShadowSkipRecord,
)
from ai_investment_agent.shadow.book import apply_buy, apply_sell
from ai_investment_agent.shadow.costs import fee_on, resolve_friction, tax_on_sell

SKIP_ACTIONS = {
    Action.NO_TRADE: ReasonCode.SHADOW_SKIPPED_NO_TRADE,
    Action.TACTICAL_WAIT: ReasonCode.SHADOW_SKIPPED_WAIT,
    Action.HOLD: ReasonCode.SHADOW_SKIPPED_HOLD,
    Action.EXIT_REVIEW: ReasonCode.SHADOW_SKIPPED_EXIT_REVIEW,
}


class ShadowExecutor:
    """Virtual fills only. There is no submit/live/broker method on this type."""

    def __init__(self, cost_model: ShadowCostModel | None = None) -> None:
        self.cost_model = cost_model or ShadowCostModel()

    def apply(
        self,
        proposal: TradeProposal,
        quote: ShadowMarketQuote | None,
        portfolio: ShadowPortfolio,
        *,
        ai_capital_limit: Decimal,
        now: datetime,
    ) -> tuple[ShadowExecutionResult, ShadowSkipRecord | None]:
        side = ShadowSide.SELL if proposal.action is Action.SELL else ShadowSide.BUY
        if proposal.action in SKIP_ACTIONS:
            reason = SKIP_ACTIONS[proposal.action].value
            order = _order(
                proposal,
                side,
                Decimal(0),
                now,
                ShadowOrderStatus.SKIPPED,
                [reason],
            )
            skip = ShadowSkipRecord(
                decision_id=proposal.decision_id,
                ticker=proposal.ticker,
                action=proposal.action,
                mid=None if quote is None else quote.mid,
                at=now,
                regime=proposal.market_regime.regime,
                horizon=proposal.horizon,
                reason_codes=[reason],
            )
            return (
                ShadowExecutionResult(order=order, fill=None, portfolio=portfolio, skipped=True),
                skip,
            )

        if proposal.action is Action.BUY:
            return self._buy(proposal, quote, portfolio, ai_capital_limit, now), None
        if proposal.action is Action.SELL:
            return self._sell(proposal, quote, portfolio, now), None

        order = _order(
            proposal,
            ShadowSide.SELL,
            Decimal(0),
            now,
            ShadowOrderStatus.SKIPPED,
            [ReasonCode.SHADOW_SKIPPED_HOLD.value],
        )
        return ShadowExecutionResult(order=order, fill=None, portfolio=portfolio, skipped=True), None

    def _buy(
        self,
        proposal: TradeProposal,
        quote: ShadowMarketQuote | None,
        portfolio: ShadowPortfolio,
        ai_capital_limit: Decimal,
        now: datetime,
    ) -> ShadowExecutionResult:
        intended = (ai_capital_limit * proposal.suggested_capital_pct / Decimal("100")).quantize(
            Decimal("1")
        )
        if quote is None or quote.ticker != proposal.ticker:
            order = _order(
                proposal,
                ShadowSide.BUY,
                intended,
                now,
                ShadowOrderStatus.REJECTED,
                [ReasonCode.SHADOW_REJECTED_NO_QUOTE.value],
            )
            return ShadowExecutionResult(order=order, portfolio=portfolio)
        friction, reasons = resolve_friction(quote, ShadowSide.BUY, self.cost_model)
        if friction is None:
            order = _order(
                proposal, ShadowSide.BUY, intended, now, ShadowOrderStatus.REJECTED, reasons
            )
            return ShadowExecutionResult(order=order, portfolio=portfolio)
        qty = (intended / friction.fill_price).quantize(Decimal("1"), rounding=ROUND_FLOOR)
        if qty <= 0:
            order = _order(
                proposal,
                ShadowSide.BUY,
                intended,
                now,
                ShadowOrderStatus.REJECTED,
                reasons + [ReasonCode.SHADOW_REJECTED_ZERO_QTY.value],
            )
            return ShadowExecutionResult(order=order, portfolio=portfolio)
        notional = qty * friction.fill_price
        fee = fee_on(notional, self.cost_model)
        cash_delta = -(notional + fee)
        while qty > 0 and portfolio.cash + cash_delta < 0:
            qty -= Decimal("1")
            notional = qty * friction.fill_price
            fee = fee_on(notional, self.cost_model)
            cash_delta = -(notional + fee)
        if qty <= 0:
            order = _order(
                proposal,
                ShadowSide.BUY,
                intended,
                now,
                ShadowOrderStatus.REJECTED,
                reasons + [ReasonCode.SHADOW_REJECTED_INSUFFICIENT_CASH.value],
            )
            return ShadowExecutionResult(order=order, portfolio=portfolio)
        order = _order(
            proposal, ShadowSide.BUY, intended, now, ShadowOrderStatus.FILLED, reasons
        )
        fill = ShadowFill(
            shadow_fill_id=new_shadow_fill_id(),
            shadow_order_id=order.shadow_order_id,
            decision_id=proposal.decision_id,
            ticker=proposal.ticker,
            side=ShadowSide.BUY,
            quantity=qty,
            mid_price=quote.mid,
            fill_price=friction.fill_price,
            spread_bps_applied=friction.spread_bps,
            slippage_bps_applied=friction.slippage_bps,
            fee=fee,
            tax=Decimal(0),
            notional=notional,
            cash_delta=cash_delta,
            filled_at=now,
            liquidity_score=friction.liquidity,
        )
        book = apply_buy(portfolio, fill, proposal.horizon)
        return ShadowExecutionResult(order=order, fill=fill, portfolio=book)

    def _sell(
        self,
        proposal: TradeProposal,
        quote: ShadowMarketQuote | None,
        portfolio: ShadowPortfolio,
        now: datetime,
    ) -> ShadowExecutionResult:
        held = next((item for item in portfolio.positions if item.ticker == proposal.ticker), None)
        if held is None or held.quantity <= 0:
            order = _order(
                proposal,
                ShadowSide.SELL,
                Decimal(0),
                now,
                ShadowOrderStatus.REJECTED,
                [ReasonCode.SHADOW_REJECTED_NO_POSITION.value],
            )
            return ShadowExecutionResult(order=order, portfolio=portfolio)
        if quote is None or quote.ticker != proposal.ticker:
            order = _order(
                proposal,
                ShadowSide.SELL,
                held.market_value,
                now,
                ShadowOrderStatus.REJECTED,
                [ReasonCode.SHADOW_REJECTED_NO_QUOTE.value],
            )
            return ShadowExecutionResult(order=order, portfolio=portfolio)
        friction, reasons = resolve_friction(quote, ShadowSide.SELL, self.cost_model)
        if friction is None:
            order = _order(
                proposal,
                ShadowSide.SELL,
                held.market_value,
                now,
                ShadowOrderStatus.REJECTED,
                reasons,
            )
            return ShadowExecutionResult(order=order, portfolio=portfolio)
        qty = held.quantity
        notional = qty * friction.fill_price
        fee = fee_on(notional, self.cost_model)
        tax = tax_on_sell(notional, self.cost_model)
        cash_delta = notional - fee - tax
        order = _order(
            proposal, ShadowSide.SELL, notional, now, ShadowOrderStatus.FILLED, reasons
        )
        fill = ShadowFill(
            shadow_fill_id=new_shadow_fill_id(),
            shadow_order_id=order.shadow_order_id,
            decision_id=proposal.decision_id,
            ticker=proposal.ticker,
            side=ShadowSide.SELL,
            quantity=qty,
            mid_price=quote.mid,
            fill_price=friction.fill_price,
            spread_bps_applied=friction.spread_bps,
            slippage_bps_applied=friction.slippage_bps,
            fee=fee,
            tax=tax,
            notional=notional,
            cash_delta=cash_delta,
            filled_at=now,
            liquidity_score=friction.liquidity,
        )
        book = apply_sell(portfolio, fill)
        return ShadowExecutionResult(order=order, fill=fill, portfolio=book)


def _order(
    proposal: TradeProposal,
    side: ShadowSide,
    notional: Decimal,
    now: datetime,
    status: ShadowOrderStatus,
    reasons: list[str],
) -> ShadowOrder:
    return ShadowOrder(
        shadow_order_id=new_shadow_order_id(),
        decision_id=proposal.decision_id,
        ticker=proposal.ticker,
        side=side,
        intended_notional=notional,
        submitted_at=now,
        status=status,
        reason_codes=reasons,
    )
