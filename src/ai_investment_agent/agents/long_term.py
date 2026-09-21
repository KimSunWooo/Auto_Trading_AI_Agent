from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.decision.utility import compute_utility
from ai_investment_agent.domain.agent_views import AgentAssessment, LongTermFeatures
from ai_investment_agent.domain.enums import Horizon, Stance
from ai_investment_agent.policy.utility import UtilityConfig


class LongTermAgent:
    """Independent long-horizon judgment. Does not read the short-term score."""

    def __init__(self, config: UtilityConfig | None = None) -> None:
        self.config = config or UtilityConfig()

    def assess(self, features: LongTermFeatures) -> AgentAssessment:
        missing = _missing_long(features)
        score, drivers, invalidations, expected = _score_long(features)
        confidence = _confidence(features, missing)
        stance = _stance(score, expected, missing, self.config)
        utility = compute_utility(
            expected,
            volatility=features.volatility,
            drawdown=features.drawdown,
            confidence=confidence,
            last_price=features.last_price,
            config=self.config,
        )
        return AgentAssessment(
            horizon=Horizon.LONG_TERM,
            stance=stance,
            confidence=confidence,
            utility=utility,
            drivers=drivers,
            invalidations=invalidations,
            missing_features=missing,
        )


def _missing_long(features: LongTermFeatures) -> list[str]:
    missing: list[str] = []
    mapping = {
        "daily_trend": features.daily_trend,
        "weekly_trend": features.weekly_trend,
        "ma20": features.ma20,
        "ma60": features.ma60,
        "ma120": features.ma120,
        "momentum": features.momentum,
        "drawdown": features.drawdown,
        "fundamentals_score": features.fundamentals_score,
        "valuation_score": features.valuation_score,
        "sector_strength": features.sector_strength,
        "macro_risk": features.macro_risk,
        "long_horizon_event_bias": features.long_horizon_event_bias,
    }
    for name, value in mapping.items():
        if value is None:
            missing.append(name)
    return missing


def _score_long(
    features: LongTermFeatures,
) -> tuple[float, list[str], list[str], Decimal | None]:
    signals: list[float] = []
    drivers: list[str] = []
    invalidations: list[str] = []

    for name, value in (("daily_trend", features.daily_trend), ("weekly_trend", features.weekly_trend)):
        if value is None:
            continue
        signals.append(float(value))
        if value > 0:
            drivers.append(f"{name}_up")
        elif value < 0:
            invalidations.append(f"{name}_down")

    aligned = _ma_alignment(features)
    if aligned is True:
        signals.append(0.4)
        drivers.append("ma_alignment")
    elif aligned is False:
        signals.append(-0.4)
        invalidations.append("ma_breakdown")

    if features.momentum is not None:
        signals.append(float(features.momentum) * 2)
        if features.momentum > 0:
            drivers.append("momentum")
        elif features.momentum < 0:
            invalidations.append("momentum_fade")

    if features.sector_strength is not None:
        signals.append(float(features.sector_strength))
        if features.sector_strength > 0:
            drivers.append("sector_strength")
        else:
            invalidations.append("sector_breakdown")

    if features.fundamentals_score is not None:
        signals.append((float(features.fundamentals_score) - 0.5) * 0.8)
        if features.fundamentals_score >= Decimal("0.55"):
            drivers.append("earnings_recovery")
        elif features.fundamentals_score <= Decimal("0.45"):
            invalidations.append("earnings_downgrade")

    if features.valuation_score is not None:
        signals.append((float(features.valuation_score) - 0.5) * 0.5)

    if features.macro_risk is not None:
        signals.append(-float(features.macro_risk))
        if features.macro_risk >= Decimal("0.5"):
            invalidations.append("macro_risk")

    if features.long_horizon_event_bias is not None:
        signals.append(float(features.long_horizon_event_bias))
        if features.long_horizon_event_bias > 0:
            drivers.append("long_horizon_event")
        elif features.long_horizon_event_bias < 0:
            invalidations.append("long_horizon_event_risk")

    if features.drawdown is not None and features.drawdown >= Decimal("0.15"):
        signals.append(-0.5)
        invalidations.append("deep_drawdown")

    if not signals:
        return 0.0, drivers, invalidations, None

    avg = sum(signals) / len(signals)
    expected = Decimal(str(round(avg * 0.18, 8)))
    return avg, _unique(drivers), _unique(invalidations), expected


def _ma_alignment(features: LongTermFeatures) -> bool | None:
    price, ma20, ma60, ma120 = features.last_price, features.ma20, features.ma60, features.ma120
    present = [item for item in (price, ma20, ma60, ma120) if item is not None]
    if len(present) < 2:
        return None
    ordered = [item for item in (price, ma20, ma60, ma120) if item is not None]
    # Compare adjacent present averages from short to long when price is present.
    if price is not None and ma20 is not None and ma60 is not None and ma120 is not None:
        if price >= ma20 >= ma60 >= ma120:
            return True
        if price < ma20 < ma60:
            return False
        return price > ma20
    if price is not None and ma20 is not None:
        return price >= ma20
    return ordered[0] >= ordered[-1]


def _confidence(features: LongTermFeatures, missing: list[str]) -> float:
    optional = {
        "fundamentals_score",
        "valuation_score",
        "ma120",
        "sector_strength",
        "long_horizon_event_bias",
    }
    required_missing = [name for name in missing if name not in optional]
    penalty = 0.08 * len(required_missing) + 0.03 * len([name for name in missing if name in optional])
    base = 0.75
    if features.daily_trend is not None and features.weekly_trend is not None:
        base = 0.82
    return max(0.2, min(0.95, base - penalty))


def _stance(score: float, expected: Decimal | None, missing: list[str], cfg: UtilityConfig) -> Stance:
    core = {"daily_trend", "weekly_trend", "momentum", "ma20"}
    if expected is None or len(core.intersection(missing)) == len(core):
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
