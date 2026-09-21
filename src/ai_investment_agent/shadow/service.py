"""In-process shadow trading. No live order conversion exists on this service."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ai_investment_agent.adapters.fixtures.portfolio import fixture_capital
from ai_investment_agent.domain.capital import CapitalContext
from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.shadow import (
    ShadowCostModel,
    ShadowExecutionResult,
    ShadowMarketQuote,
    ShadowPortfolio,
)
from ai_investment_agent.shadow.book import mark_positions
from ai_investment_agent.shadow.executor import ShadowExecutor
from ai_investment_agent.shadow.performance import ShadowPerformanceReport, ShadowPerformanceTracker


class ShadowTradingService:
    """Owns the AI virtual account. Does not import or call a broker."""

    def __init__(
        self,
        capital: CapitalContext | None = None,
        cost_model: ShadowCostModel | None = None,
    ) -> None:
        self.capital = capital or fixture_capital()
        self.portfolio = ShadowPortfolio.opened(self.capital)
        self.executor = ShadowExecutor(cost_model)
        self.results: list[ShadowExecutionResult] = []
        self.tracker = ShadowPerformanceTracker()

    def apply_snapshot(
        self,
        snapshot: DecisionSnapshot,
        quote: ShadowMarketQuote | None = None,
        *,
        now: datetime | None = None,
    ) -> ShadowExecutionResult:
        moment = now or snapshot.created_at
        market_quote = quote or ShadowMarketQuote.from_snapshot(snapshot.market_snapshot)
        before_realized = self.portfolio.realized_pnl
        result, skip = self.executor.apply(
            snapshot.proposal,
            market_quote,
            self.portfolio,
            ai_capital_limit=self.capital.ai_capital_limit,
            now=moment,
        )
        self.portfolio = result.portfolio
        self.results.append(result)
        self.tracker.record_result(
            result,
            horizon=snapshot.proposal.horizon,
            regime=snapshot.proposal.market_regime.regime,
            skip=skip,
            realized_pnl_delta=result.portfolio.realized_pnl - before_realized,
        )
        if market_quote is not None:
            self.tracker.note_mids({market_quote.ticker: market_quote.mid})
        return result

    def mark_to_market(
        self, quotes: dict[str, ShadowMarketQuote], *, at: datetime
    ) -> ShadowPortfolio:
        prices = {ticker: quote.mid for ticker, quote in quotes.items()}
        self.portfolio = mark_positions(self.portfolio, prices, at)
        self.tracker.equity_curve.append(self.portfolio.equity)
        self.tracker.peak_drawdown = max(self.tracker.peak_drawdown, self.portfolio.drawdown)
        self.tracker.note_mids(prices)
        return self.portfolio

    def performance(
        self, later_mids: dict[str, Decimal] | None = None, *, now: datetime | None = None
    ) -> ShadowPerformanceReport:
        return self.tracker.report(self.portfolio, later_mids, now=now)
