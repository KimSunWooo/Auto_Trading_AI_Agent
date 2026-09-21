from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.decision.utility import compute_utility
from ai_investment_agent.domain.agent_views import AgentAssessment, ShortTermFeatures
from ai_investment_agent.domain.enums import Horizon, Stance
from ai_investment_agent.policy.utility import UtilityConfig


class ShortTermAgent:
    """Independent short-horizon judgment. Does not read the long-term score."""

    def __init__(self, config: UtilityConfig | None = None) -> None:
        self.config = config or UtilityConfig()

    def assess(self, features: ShortTermFeatures) -> AgentAssessment:
        missing = _missing_short(features)
        score, drivers, invalidations, expected = _score_short(features)
        confidence = _confidence(missing)
        stance = _stance(score, expected, missing, self.config)
        utility = compute_utility(
            expected,
            volatility=features.volatility,
            drawdown=None,
            confidence=confidence,
            spread=features.spread,
            last_price=features.last_price,
            config=self.config,
        )
        return AgentAssessment(
            horizon=Horizon.SHORT_TERM,
            stance=stance,
            confidence=confidence,
            utility=utility,
            drivers=drivers,
            invalidations=invalidations,
            missing_features=missing,
        )


def _missing_short(features: ShortTermFeatures) -> list[str]:
    missing: list[str] = []
    mapping = {
        "intraday_trend": features.intraday_trend,
        "ohlcv_1m": features.ohlcv_1m,
        "ohlcv_5m": features.ohlcv_5m,
        "ohlcv_15m": features.ohlcv_15m,
        "vwap": features.vwap,
        "volume_spike": features.volume_spike,
        "momentum": features.momentum,
        "breakout": features.breakout,
        "volatility": features.volatility,
        "liquidity": features.liquidity,
        "spread": features.spread,
        "short_lived_event_bias": features.short_lived_event_bias,
    }
    for name, value in mapping.items():
        if value is None:
            missing.append(name)
    return missing


def _score_short(
    features: ShortTermFeatures,
) -> tuple[float, list[str], list[str], Decimal | None]:
    signals: list[float] = []
    drivers: list[str] = []
    invalidations: list[str] = []

    if features.intraday_trend is not None:
        signals.append(float(features.intraday_trend))
        if features.intraday_trend > 0:
            drivers.append("intraday_trend_up")
        elif features.intraday_trend < 0:
            invalidations.append("intraday_trend_down")

    if features.momentum is not None:
        signals.append(float(features.momentum) * 2)
        if features.momentum > 0:
            drivers.append("short_momentum")
        elif features.momentum < 0:
            invalidations.append("short_momentum_down")

    if features.volume_spike is not None:
        spike = float(features.volume_spike)
        if spike >= 1.8:
            drivers.append("volume_spike")
            direction = features.intraday_trend or features.momentum or Decimal("0")
            signals.append(0.25 if direction >= 0 else -0.25)

    if features.breakout is not None:
        signals.append(float(features.breakout) * 0.5)
        if features.breakout > 0:
            drivers.append("breakout")

    if features.liquidity is not None and features.liquidity <= Decimal("0.25"):
        signals.append(-0.4)
        invalidations.append("low_liquidity")

    if features.short_lived_event_bias is not None:
        signals.append(float(features.short_lived_event_bias))
        if features.short_lived_event_bias > 0:
            drivers.append("short_lived_event")
        elif features.short_lived_event_bias < 0:
            invalidations.append("short_lived_event_risk")

    if features.vwap is not None and features.last_price is not None:
        if features.last_price >= features.vwap:
            signals.append(0.15)
            drivers.append("above_vwap")
        else:
            signals.append(-0.15)
            invalidations.append("below_vwap")

    if not signals:
        return 0.0, drivers, invalidations, None

    avg = sum(signals) / len(signals)
    expected = Decimal(str(round(avg * 0.06, 8)))
    return avg, _unique(drivers), _unique(invalidations), expected


def _confidence(missing: list[str]) -> float:
    optional = {"ohlcv_1m", "ohlcv_5m", "ohlcv_15m", "vwap", "breakout", "spread"}
    required_missing = [name for name in missing if name not in optional]
    penalty = 0.07 * len(required_missing) + 0.02 * len([name for name in missing if name in optional])
    return max(0.2, min(0.9, 0.72 - penalty))


def _stance(score: float, expected: Decimal | None, missing: list[str], cfg: UtilityConfig) -> Stance:
    usable = {"intraday_trend", "momentum", "volume_spike", "short_lived_event_bias"}
    present = usable.difference(missing)
    if expected is None or not present:
        return Stance.WEAK
    if score >= cfg.bullish_score:
        return Stance.BULLISH
    if score <= cfg.bearish_score:
        return Stance.BEARISH
    if abs(score) < 0.12:
        return Stance.WEAK
    return Stance.NEUTRAL


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen
