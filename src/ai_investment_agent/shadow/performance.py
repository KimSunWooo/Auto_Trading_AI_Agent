"""Compare AI judgments with the shadow book. No live execution quality."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from math import sqrt
from statistics import mean, pstdev
from typing import Literal

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.enums import (
    Action,
    EvaluationStatus,
    Horizon,
    MarketRegimeType,
    ShadowSide,
)
from ai_investment_agent.domain.shadow import (
    ShadowExecutionResult,
    ShadowFill,
    ShadowPortfolio,
    ShadowSkipRecord,
)


class BucketMetrics(DomainModel):
    status: EvaluationStatus = EvaluationStatus.PENDING
    sample_size: int = 0
    win_rate: float | None = None
    average_return: Decimal | None = None


class ShadowPerformanceReport(DomainModel):
    decision_quality: BucketMetrics
    capital_allocation: BucketMetrics
    drawdown: Decimal
    max_drawdown: Decimal
    risk_adjusted_return: float | None = None
    total_return: Decimal
    no_trade_performance: BucketMetrics
    long_vs_short: dict[str, BucketMetrics] = Field(default_factory=dict)
    by_regime: dict[str, BucketMetrics] = Field(default_factory=dict)
    live_orders_placed: Literal[0] = 0
    evaluated_at: datetime | None = None


@dataclass
class _Closed:
    pnl: Decimal
    deployed: Decimal
    horizon: Horizon
    regime: MarketRegimeType
    action: Action


@dataclass
class _OpenBuy:
    fill: ShadowFill
    horizon: Horizon
    regime: MarketRegimeType


@dataclass
class ShadowPerformanceTracker:
    closed: list[_Closed] = field(default_factory=list)
    open_buys: list[_OpenBuy] = field(default_factory=list)
    skips: list[ShadowSkipRecord] = field(default_factory=list)
    equity_curve: list[Decimal] = field(default_factory=list)
    peak_drawdown: Decimal = Decimal(0)
    last_mids: dict[str, Decimal] = field(default_factory=dict)

    def record_result(
        self,
        result: ShadowExecutionResult,
        *,
        horizon: Horizon,
        regime: MarketRegimeType,
        skip: ShadowSkipRecord | None,
        realized_pnl_delta: Decimal = Decimal(0),
    ) -> None:
        self.equity_curve.append(result.portfolio.equity)
        self.peak_drawdown = max(self.peak_drawdown, result.portfolio.drawdown)
        if skip is not None:
            self.skips.append(skip)
        fill = result.fill
        if fill is None:
            return
        if fill.side is ShadowSide.BUY:
            self.open_buys.append(_OpenBuy(fill=fill, horizon=horizon, regime=regime))
            return
        if fill.side is ShadowSide.SELL:
            self.open_buys = [item for item in self.open_buys if item.fill.ticker != fill.ticker]
            self.closed.append(
                _Closed(
                    pnl=realized_pnl_delta,
                    deployed=fill.notional,
                    horizon=horizon,
                    regime=regime,
                    action=Action.SELL,
                )
            )

    def note_mids(self, mids: dict[str, Decimal]) -> None:
        self.last_mids.update(mids)

    def report(
        self,
        portfolio: ShadowPortfolio,
        later_mids: dict[str, Decimal] | None = None,
        *,
        now: datetime | None = None,
    ) -> ShadowPerformanceReport:
        later = {**self.last_mids, **(later_mids or {})}
        marked = list(self.closed)
        for item in self.open_buys:
            later_mid = later.get(item.fill.ticker)
            if later_mid is None:
                continue
            pnl = (later_mid - item.fill.fill_price) * item.fill.quantity - item.fill.fee
            marked.append(
                _Closed(
                    pnl=pnl,
                    deployed=item.fill.notional,
                    horizon=item.horizon,
                    regime=item.regime,
                    action=Action.BUY,
                )
            )
        start = self.equity_curve[0] if self.equity_curve else portfolio.ai_capital_limit
        total_return = Decimal(0) if start <= 0 else (portfolio.equity - start) / start
        return ShadowPerformanceReport(
            decision_quality=_from_pnls([item.pnl for item in marked]),
            capital_allocation=_capital_metrics(marked, portfolio),
            drawdown=portfolio.drawdown,
            max_drawdown=self.peak_drawdown,
            risk_adjusted_return=_sharpe(self.equity_curve),
            total_return=total_return,
            no_trade_performance=_no_trade_metrics(self.skips, later),
            long_vs_short={
                Horizon.LONG_TERM.value: _from_pnls(
                    [item.pnl for item in marked if item.horizon is Horizon.LONG_TERM]
                ),
                Horizon.SHORT_TERM.value: _from_pnls(
                    [item.pnl for item in marked if item.horizon is Horizon.SHORT_TERM]
                ),
            },
            by_regime=_by_regime(marked),
            evaluated_at=now,
        )


def _from_pnls(values: list[Decimal]) -> BucketMetrics:
    if not values:
        return BucketMetrics(status=EvaluationStatus.INSUFFICIENT_SAMPLE, sample_size=0)
    wins = sum(1 for item in values if item > 0)
    avg = mean(values)
    return BucketMetrics(
        status=EvaluationStatus.SCORED,
        sample_size=len(values),
        win_rate=wins / len(values),
        average_return=Decimal(str(avg)),
    )


def _capital_metrics(closed: list[_Closed], portfolio: ShadowPortfolio) -> BucketMetrics:
    if not closed:
        deployed = portfolio.deployed_notional
        pct = Decimal(0) if portfolio.ai_capital_limit <= 0 else deployed / portfolio.ai_capital_limit
        return BucketMetrics(
            status=EvaluationStatus.INSUFFICIENT_SAMPLE,
            sample_size=0,
            average_return=pct,
        )
    rets = [
        item.pnl / item.deployed if item.deployed > 0 else Decimal(0) for item in closed
    ]
    return _from_pnls(rets)


def _no_trade_metrics(
    skips: list[ShadowSkipRecord], later_mids: dict[str, Decimal]
) -> BucketMetrics:
    waits = [
        item
        for item in skips
        if item.action in {Action.NO_TRADE, Action.TACTICAL_WAIT} and item.mid is not None
    ]
    if not waits:
        return BucketMetrics(
            status=EvaluationStatus.INSUFFICIENT_SAMPLE, sample_size=len(skips)
        )
    values: list[Decimal] = []
    for item in waits:
        later = later_mids.get(item.ticker)
        if later is None or item.mid is None or item.mid <= 0:
            continue
        # Positive when skipping avoided a loss (price fell). Negative when missing a gain.
        values.append((item.mid - later) / item.mid)
    if not values:
        return BucketMetrics(status=EvaluationStatus.INSUFFICIENT_SAMPLE, sample_size=len(waits))
    return _from_pnls(values)


def _by_regime(closed: list[_Closed]) -> dict[str, BucketMetrics]:
    groups: dict[str, list[Decimal]] = defaultdict(list)
    for item in closed:
        groups[item.regime.value].append(item.pnl)
    if not groups:
        return {}
    return {key: _from_pnls(vals) for key, vals in groups.items()}


def _sharpe(curve: list[Decimal]) -> float | None:
    if len(curve) < 3:
        return None
    rets = []
    for prev, cur in pairwise(curve):
        if prev <= 0:
            continue
        rets.append(float((cur - prev) / prev))
    if len(rets) < 2:
        return None
    sigma = pstdev(rets)
    if sigma == 0:
        return None
    return mean(rets) / sigma * sqrt(len(rets))
