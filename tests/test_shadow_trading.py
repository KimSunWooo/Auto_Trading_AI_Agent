from __future__ import annotations

from decimal import Decimal
from inspect import getmembers, isfunction, ismethod
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_investment_agent.analysis.service import PIPELINE_STAGES, AnalysisService
from ai_investment_agent.api.app import create_app
from ai_investment_agent.domain.enums import (
    Action,
    EvaluationStatus,
    Horizon,
    MarketRegimeType,
    ReasonCode,
    ShadowOrderStatus,
    ShadowSide,
)
from ai_investment_agent.domain.ids import new_decision_id
from ai_investment_agent.domain.shadow import (
    ShadowFill,
    ShadowMarketQuote,
    ShadowOrder,
    ShadowPortfolio,
    ShadowPosition,
)
from ai_investment_agent.shadow.costs import resolve_friction
from ai_investment_agent.shadow.executor import ShadowExecutor
from ai_investment_agent.shadow.service import ShadowTradingService
from tests.policy_support import AS_OF, buy_proposal, sell_proposal
from tests.support import provided_capital

FORBIDDEN_METHODS = {
    "to_broker",
    "to_order",
    "submit",
    "place_order",
    "submit_order",
    "convert_to_broker",
    "to_live_order",
    "send_to_kis",
}


def _quote(
    *,
    mid: Decimal = Decimal(71000),
    spread_bps: Decimal | None = None,
    liquidity_score: Decimal | None = Decimal("0.80"),
    ticker: str = "005930",
) -> ShadowMarketQuote:
    return ShadowMarketQuote(
        ticker=ticker,
        mid=mid,
        as_of=AS_OF,
        spread_bps=spread_bps,
        liquidity_score=liquidity_score,
    )


def _proposal(
    *,
    action: Action = Action.BUY,
    pct: Decimal = Decimal(5),
    horizon: Horizon = Horizon.LONG_TERM,
    ticker: str = "005930",
    regime: MarketRegimeType = MarketRegimeType.SIDEWAYS,
):
    if action is Action.BUY:
        base = buy_proposal(ticker=ticker, pct=pct, horizon=horizon)
    elif action is Action.SELL:
        base = sell_proposal().model_copy(update={"ticker": ticker})
    else:
        holding = 252 if horizon is Horizon.LONG_TERM else 0
        skip_horizon = action in {
            Action.NO_TRADE,
            Action.TACTICAL_WAIT,
            Action.HOLD,
            Action.EXIT_REVIEW,
            Action.SELL,
        }
        base = buy_proposal(ticker=ticker, pct=Decimal(0), horizon=horizon).model_copy(
            update={
                "action": action,
                "horizon": Horizon.NONE if skip_horizon else horizon,
                "expected_holding_period": 0 if skip_horizon else holding,
                "suggested_capital_pct": Decimal(0),
            }
        )
    return base.model_copy(
        update={
            "decision_id": new_decision_id(),
            "market_regime": base.market_regime.model_copy(update={"regime": regime}),
        }
    )


def _apply(action: Action = Action.BUY, quote: ShadowMarketQuote | None = None, **kwargs):
    service = ShadowTradingService(provided_capital())
    result, skip = service.executor.apply(
        _proposal(action=action, **kwargs),
        _quote() if quote is None else quote,
        service.portfolio,
        ai_capital_limit=service.capital.ai_capital_limit,
        now=AS_OF,
    )
    return service, result, skip


def test_shadow_cash_is_ai_capital_limit_not_total():
    opened = ShadowPortfolio.opened(provided_capital())
    assert opened.cash == provided_capital().ai_capital_limit
    assert opened.cash != provided_capital().total_capital
    assert opened.initial_capital == provided_capital().total_capital
    assert opened.source == "shadow_virtual"
    assert opened.convertible_to_broker is False


def test_unknown_spread_is_not_zero_and_fill_is_not_mid():
    quote = _quote(spread_bps=None, liquidity_score=Decimal("0.80"))
    friction, reasons = resolve_friction(
        quote, ShadowSide.BUY, ShadowTradingService().executor.cost_model
    )
    assert friction is not None
    assert friction.spread_bps == Decimal(10)
    assert friction.fill_price != quote.mid
    assert friction.fill_price > quote.mid
    assert ReasonCode.SHADOW_CONSERVATIVE_SPREAD_DEFAULT.value in reasons
    assert ReasonCode.SHADOW_FILL_NOT_MID.value in reasons


def test_unknown_liquidity_is_conservative_not_perfect():
    quote = _quote(spread_bps=Decimal(8), liquidity_score=None)
    friction, reasons = resolve_friction(
        quote, ShadowSide.BUY, ShadowTradingService().executor.cost_model
    )
    assert friction is not None
    assert friction.liquidity == Decimal("0.35")
    assert friction.liquidity < Decimal(1)
    assert friction.slippage_bps > Decimal(5)
    assert ReasonCode.SHADOW_CONSERVATIVE_LIQUIDITY_DEFAULT.value in reasons


def test_low_liquidity_rejects_fill():
    _, result, _ = _apply(quote=_quote(liquidity_score=Decimal("0.10")))
    assert result.fill is None
    assert result.order.status is ShadowOrderStatus.REJECTED
    assert ReasonCode.SHADOW_REJECTED_LOW_LIQUIDITY.value in result.order.reason_codes
    assert result.portfolio.positions == []


def test_buy_fill_is_above_mid_and_pays_fees():
    _, result, skip = _apply()
    assert skip is None
    fill = result.fill
    assert fill is not None
    assert fill.side is ShadowSide.BUY
    assert fill.fill_price > fill.mid_price
    assert fill.fee > 0
    assert fill.tax == 0
    assert fill.cash_delta == -(fill.notional + fill.fee)
    assert result.portfolio.cash < provided_capital().ai_capital_limit
    assert result.portfolio.positions[0].quantity == fill.quantity
    assert fill.shadow_fill_id.startswith("shf_")
    assert result.order.shadow_order_id.startswith("sho_")
    assert result.broker_called is False
    assert result.live_order_placed is False


def test_sell_fill_is_below_mid_and_charges_tax():
    service = ShadowTradingService(provided_capital())
    buy, _ = service.executor.apply(
        _proposal(action=Action.BUY),
        _quote(),
        service.portfolio,
        ai_capital_limit=service.capital.ai_capital_limit,
        now=AS_OF,
    )
    service.portfolio = buy.portfolio
    sell, _ = service.executor.apply(
        _proposal(action=Action.SELL),
        _quote(),
        service.portfolio,
        ai_capital_limit=service.capital.ai_capital_limit,
        now=AS_OF,
    )
    fill = sell.fill
    assert fill is not None
    assert fill.fill_price < fill.mid_price
    assert fill.fee > 0
    assert fill.tax > 0
    assert sell.portfolio.positions == []
    assert sell.portfolio.realized_pnl < 0
    assert sell.portfolio.cash < provided_capital().ai_capital_limit


def test_no_trade_does_not_open_a_position():
    _, result, skip = _apply(action=Action.NO_TRADE)
    assert result.skipped is True
    assert result.fill is None
    assert result.order.status is ShadowOrderStatus.SKIPPED
    assert ReasonCode.SHADOW_SKIPPED_NO_TRADE.value in result.order.reason_codes
    assert result.portfolio.positions == []
    assert result.portfolio.cash == provided_capital().ai_capital_limit
    assert skip is not None
    assert skip.action is Action.NO_TRADE


def test_wait_hold_and_exit_review_are_skipped_not_sold():
    for action, code in (
        (Action.TACTICAL_WAIT, ReasonCode.SHADOW_SKIPPED_WAIT),
        (Action.HOLD, ReasonCode.SHADOW_SKIPPED_HOLD),
        (Action.EXIT_REVIEW, ReasonCode.SHADOW_SKIPPED_EXIT_REVIEW),
    ):
        _, result, skip = _apply(action=action)
        assert result.skipped is True
        assert result.fill is None
        assert code.value in result.order.reason_codes
        assert skip is not None


def test_drawdown_after_mark_to_market():
    service = ShadowTradingService(provided_capital())
    bought, _ = service.executor.apply(
        _proposal(action=Action.BUY, pct=Decimal(40)),
        _quote(mid=Decimal(71000)),
        service.portfolio,
        ai_capital_limit=service.capital.ai_capital_limit,
        now=AS_OF,
    )
    service.portfolio = bought.portfolio
    later = _quote(mid=Decimal(50000))
    marked = service.mark_to_market({later.ticker: later}, at=AS_OF)
    assert marked.unrealized_pnl < 0
    assert marked.drawdown > 0
    assert marked.equity < marked.peak_equity


def test_performance_axes_include_no_trade_long_short_and_regime():
    service = ShadowTradingService(provided_capital())
    long_buy, skip = service.executor.apply(
        _proposal(action=Action.BUY, horizon=Horizon.LONG_TERM, regime=MarketRegimeType.BULL),
        _quote(),
        service.portfolio,
        ai_capital_limit=service.capital.ai_capital_limit,
        now=AS_OF,
    )
    service.portfolio = long_buy.portfolio
    service.tracker.record_result(
        long_buy,
        horizon=Horizon.LONG_TERM,
        regime=MarketRegimeType.BULL,
        skip=skip,
    )
    short_buy, skip = service.executor.apply(
        _proposal(
            action=Action.BUY,
            horizon=Horizon.SHORT_TERM,
            ticker="000660",
            regime=MarketRegimeType.BEAR,
        ),
        _quote(ticker="000660"),
        service.portfolio,
        ai_capital_limit=service.capital.ai_capital_limit,
        now=AS_OF,
    )
    service.portfolio = short_buy.portfolio
    service.tracker.record_result(
        short_buy,
        horizon=Horizon.SHORT_TERM,
        regime=MarketRegimeType.BEAR,
        skip=skip,
    )
    no_trade, skip = service.executor.apply(
        _proposal(action=Action.NO_TRADE),
        _quote(),
        service.portfolio,
        ai_capital_limit=service.capital.ai_capital_limit,
        now=AS_OF,
    )
    service.portfolio = no_trade.portfolio
    service.tracker.record_result(
        no_trade,
        horizon=Horizon.NONE,
        regime=MarketRegimeType.SIDEWAYS,
        skip=skip,
    )
    report = service.performance(
        {"005930": Decimal(69000), "000660": Decimal(80000)},
        now=AS_OF,
    )
    assert report.live_orders_placed == 0
    assert report.decision_quality.status is EvaluationStatus.SCORED
    assert report.capital_allocation.sample_size >= 1
    assert report.no_trade_performance.status is EvaluationStatus.SCORED
    assert report.no_trade_performance.average_return is not None
    assert report.no_trade_performance.average_return > 0
    assert report.long_vs_short[Horizon.LONG_TERM.value].sample_size == 1
    assert report.long_vs_short[Horizon.SHORT_TERM.value].sample_size == 1
    assert MarketRegimeType.BULL.value in report.by_regime
    assert MarketRegimeType.BEAR.value in report.by_regime


def test_fill_cannot_equal_mid():
    with pytest.raises(ValidationError):
        ShadowFill(
            shadow_fill_id="shf_" + "a" * 32,
            shadow_order_id="sho_" + "b" * 32,
            decision_id=new_decision_id(),
            ticker="005930",
            side=ShadowSide.BUY,
            quantity=Decimal(1),
            mid_price=Decimal(71000),
            fill_price=Decimal(71000),
            spread_bps_applied=Decimal(0),
            slippage_bps_applied=Decimal(0),
            fee=Decimal(0),
            tax=Decimal(0),
            notional=Decimal(71000),
            cash_delta=Decimal(-71000),
            filled_at=AS_OF,
        )


def test_convertible_to_broker_cannot_be_true():
    with pytest.raises(ValidationError):
        ShadowOrder(
            shadow_order_id="sho_" + "c" * 32,
            decision_id=new_decision_id(),
            ticker="005930",
            side=ShadowSide.BUY,
            intended_notional=Decimal(1),
            submitted_at=AS_OF,
            status=ShadowOrderStatus.SKIPPED,
            convertible_to_broker=True,  # type: ignore[arg-type]
        )


def test_no_conversion_methods_or_broker_ids():
    types = (
        ShadowExecutor,
        ShadowTradingService,
        ShadowOrder,
        ShadowFill,
        ShadowPosition,
        ShadowPortfolio,
    )
    for typ in types:
        names = {name for name, member in getmembers(typ) if isfunction(member) or ismethod(member)}
        assert names.isdisjoint(FORBIDDEN_METHODS)
        assert not any(name.startswith(("to_broker", "place_")) for name in names)
    files = list(Path("src/ai_investment_agent/shadow").glob("*.py"))
    files.append(Path("src/ai_investment_agent/domain/shadow.py"))
    joined = "\n".join(path.read_text() for path in files)
    for needle in ("def to_broker", "def to_order", "def place_order", "def submit_order"):
        assert needle not in joined
    order = ShadowOrder(
        shadow_order_id="sho_" + "d" * 32,
        decision_id=new_decision_id(),
        ticker="005930",
        side=ShadowSide.BUY,
        intended_notional=Decimal(0),
        submitted_at=AS_OF,
        status=ShadowOrderStatus.SKIPPED,
    )
    dumped = order.model_dump(mode="json")
    assert dumped["convertibleToBroker"] is False
    assert "brokerOrderId" not in dumped
    assert "broker_order_id" not in dumped


def test_analysis_pipeline_runs_shadow_without_live_orders():
    service = AnalysisService()
    result = service.evaluate("005930")
    assert result.orders_placed == 0
    assert result.broker_called is False
    assert result.pipeline[-1] == "SHADOW_EXECUTION"
    assert result.pipeline == list(PIPELINE_STAGES)
    assert result.shadow_execution is not None
    assert result.shadow_execution.broker_called is False
    assert result.shadow_execution.live_order_placed is False
    assert result.shadow_execution.order.convertible_to_broker is False


def test_shadow_read_api_is_not_an_order_route():
    client = TestClient(create_app(AnalysisService()))
    evaluated = client.post("/analysis/evaluate", json={"ticker": "005930"})
    assert evaluated.status_code == 200
    body = evaluated.json()
    assert body["ordersPlaced"] == 0
    assert body["shadowExecution"]["liveOrderPlaced"] is False
    portfolio = client.get("/shadow/portfolio")
    assert portfolio.status_code == 200
    book = portfolio.json()
    assert book["source"] == "shadow_virtual"
    assert book["convertibleToBroker"] is False
    report = client.get("/shadow/performance")
    assert report.status_code == 200
    assert report.json()["liveOrdersPlaced"] == 0
    assert client.post("/shadow/portfolio").status_code == 405
