from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.agent_views import UtilityBreakdown
from ai_investment_agent.policy.utility import UtilityConfig


def compute_utility(
    expected_return: Decimal | None,
    *,
    volatility: Decimal | None,
    drawdown: Decimal | None,
    confidence: float,
    spread: Decimal | None = None,
    last_price: Decimal | None = None,
    config: UtilityConfig | None = None,
) -> UtilityBreakdown:
    """Net edge = E[r] - risk - cost - slippage - drawdown - tail - uncertainty.

    Missing market inputs are not filled with optimistic zeros. Vol uses the
    configured missing-vol penalty. Spread, if absent, uses policy base slippage.
    """

    cfg = config or UtilityConfig()
    if expected_return is None:
        return UtilityBreakdown(
            expected_return=None,
            risk_penalty=_vol_penalty(volatility, cfg),
            transaction_cost=cfg.transaction_cost,
            slippage=_slippage(spread, last_price, cfg),
            drawdown_penalty=_dd_penalty(drawdown, cfg),
            tail_risk=_tail(volatility, cfg),
            uncertainty_penalty=_uncertainty(confidence, cfg),
            net_edge=None,
        )

    risk = _vol_penalty(volatility, cfg)
    cost = cfg.transaction_cost
    slip = _slippage(spread, last_price, cfg)
    dd = _dd_penalty(drawdown, cfg)
    tail = _tail(volatility, cfg)
    unc = _uncertainty(confidence, cfg)
    net = expected_return - risk - cost - slip - dd - tail - unc
    return UtilityBreakdown(
        expected_return=expected_return,
        risk_penalty=risk,
        transaction_cost=cost,
        slippage=slip,
        drawdown_penalty=dd,
        tail_risk=tail,
        uncertainty_penalty=unc,
        net_edge=net,
    )


def _vol_penalty(volatility: Decimal | None, cfg: UtilityConfig) -> Decimal:
    vol = cfg.missing_vol_penalty if volatility is None else volatility
    return cfg.risk_coeff * _nonneg(vol)


def _dd_penalty(drawdown: Decimal | None, cfg: UtilityConfig) -> Decimal:
    if drawdown is None:
        return Decimal("0")
    return cfg.drawdown_coeff * _nonneg(drawdown)


def _tail(volatility: Decimal | None, cfg: UtilityConfig) -> Decimal:
    vol = cfg.missing_vol_penalty if volatility is None else volatility
    return cfg.tail_coeff * _nonneg(vol)


def _uncertainty(confidence: float, cfg: UtilityConfig) -> Decimal:
    gap = Decimal(str(round(max(0.0, min(1.0, 1.0 - confidence)), 6)))
    return cfg.uncertainty_coeff * gap


def _slippage(spread: Decimal | None, last_price: Decimal | None, cfg: UtilityConfig) -> Decimal:
    if spread is not None and last_price not in (None, Decimal("0")):
        implied = spread / last_price
        return implied if implied > cfg.base_slippage else cfg.base_slippage
    return cfg.base_slippage


def _nonneg(value: Decimal) -> Decimal:
    return value if value > 0 else Decimal("0")
