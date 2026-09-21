"""Net-edge utility coefficients. Not inferred from missing market data."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class UtilityConfig:
    min_net_edge: Decimal = Decimal("0.010")
    dominance_margin: Decimal = Decimal("0.005")
    risk_coeff: Decimal = Decimal("0.40")
    transaction_cost: Decimal = Decimal("0.001")
    base_slippage: Decimal = Decimal("0.001")
    drawdown_coeff: Decimal = Decimal("0.35")
    tail_coeff: Decimal = Decimal("0.25")
    uncertainty_coeff: Decimal = Decimal("0.08")
    missing_vol_penalty: Decimal = Decimal("0.08")
    stretched_extension: Decimal = Decimal("0.03")
    priced_in_wait: float = 0.70
    remaining_edge_wait: float = 0.20
    bullish_score: float = 0.25
    bearish_score: float = -0.25
