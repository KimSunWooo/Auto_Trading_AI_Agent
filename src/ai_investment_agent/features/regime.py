from __future__ import annotations

from datetime import datetime

from ai_investment_agent.domain.context import EventImpactFeatures, QuantitativeFeatures
from ai_investment_agent.domain.enums import MarketRegimeType
from ai_investment_agent.domain.market import MarketRegime
from ai_investment_agent.features.mathutil import as_float
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig


class FeatureRegimeClassifier:
    """Deterministic regime from features. UNKNOWN is never treated as safe."""

    def __init__(self, config: FeaturePolicyConfig | None = None) -> None:
        self.config = config or FeaturePolicyConfig()

    def classify(
        self,
        quantitative: QuantitativeFeatures,
        events: EventImpactFeatures,
        *,
        as_of: datetime,
        bar_count: int,
    ) -> MarketRegime:
        cfg = self.config
        flags: list[MarketRegimeType] = []
        vol = as_float(quantitative.volatility)
        liq = as_float(quantitative.liquidity)
        drawdown = as_float(quantitative.drawdown)
        ret = as_float(quantitative.return_5d) or as_float(quantitative.return_1d)
        trend = as_float(quantitative.trend)

        if bar_count < cfg.min_bars_for_regime or (
            quantitative.return_1d is None and quantitative.volatility is None
        ):
            return MarketRegime(
                regime=MarketRegimeType.UNKNOWN,
                confidence=0.0,
                as_of=as_of,
                explanation="Insufficient market path. UNKNOWN is not a safe or normal regime.",
                detected_from="feature-regime",
                flags=[],
            )

        if drawdown is not None and drawdown >= cfg.crisis_drawdown:
            flags.append(MarketRegimeType.CRISIS)
        if events.effective_impact >= cfg.event_risk_threshold:
            flags.append(MarketRegimeType.EVENT_RISK)
        if liq is not None and liq <= cfg.low_liquidity_threshold:
            flags.append(MarketRegimeType.LOW_LIQUIDITY)
        if vol is not None and vol >= cfg.high_vol_threshold:
            flags.append(MarketRegimeType.HIGH_VOLATILITY)
        elif vol is not None and vol <= cfg.low_vol_threshold:
            flags.append(MarketRegimeType.LOW_VOLATILITY)
        if ret is not None and ret >= cfg.bull_return_threshold and (trend is None or trend >= 0):
            flags.append(MarketRegimeType.BULL)
        if ret is not None and ret <= cfg.bear_return_threshold and (trend is None or trend <= 0):
            flags.append(MarketRegimeType.BEAR)
        if MarketRegimeType.BULL not in flags and MarketRegimeType.BEAR not in flags:
            flags.append(MarketRegimeType.SIDEWAYS)

        primary = _primary(flags)
        unique_flags = _unique([item for item in flags if item is not primary])
        explanation = _explain(primary, events)
        confidence = 0.55
        if primary is MarketRegimeType.EVENT_RISK:
            confidence = min(0.9, 0.5 + events.effective_impact)
        if primary is MarketRegimeType.CRISIS:
            confidence = 0.8
        return MarketRegime(
            regime=primary,
            confidence=confidence,
            as_of=as_of,
            explanation=explanation,
            detected_from="feature-regime",
            flags=unique_flags,
        )


_PRIORITY = (
    MarketRegimeType.CRISIS,
    MarketRegimeType.EVENT_RISK,
    MarketRegimeType.LOW_LIQUIDITY,
    MarketRegimeType.HIGH_VOLATILITY,
    MarketRegimeType.BEAR,
    MarketRegimeType.BULL,
    MarketRegimeType.LOW_VOLATILITY,
    MarketRegimeType.SIDEWAYS,
)


def _primary(flags: list[MarketRegimeType]) -> MarketRegimeType:
    for candidate in _PRIORITY:
        if candidate in flags:
            return candidate
    return MarketRegimeType.SIDEWAYS


def _unique(values: list[MarketRegimeType]) -> list[MarketRegimeType]:
    seen: list[MarketRegimeType] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _explain(primary: MarketRegimeType, events: EventImpactFeatures) -> str:
    if primary is MarketRegimeType.UNKNOWN:
        return "UNKNOWN is not a safe or normal regime."
    if primary is MarketRegimeType.EVENT_RISK:
        return (
            f"Elevated event risk (effectiveImpact={events.effective_impact:.3f}). "
            "Not a BUY/SELL signal."
        )
    if primary is MarketRegimeType.CRISIS:
        return "Drawdown breached crisis threshold."
    return f"Primary regime {primary.value} from deterministic features."
