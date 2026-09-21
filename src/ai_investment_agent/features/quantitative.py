from __future__ import annotations

from datetime import datetime

from ai_investment_agent.domain.context import PriceSeries, QuantitativeFeatures
from ai_investment_agent.features.mathutil import (
    max_drawdown,
    moving_average,
    sample_std,
    simple_returns,
    to_decimal,
    window_return,
)
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig


class QuantitativeFeatureCalculator:
    """Deterministic market-data features. Never calls an LLM."""

    def __init__(self, config: FeaturePolicyConfig | None = None) -> None:
        self.config = config or FeaturePolicyConfig()

    def compute(
        self,
        series: PriceSeries,
        *,
        as_of: datetime,
        liquidity: float | None = None,
        benchmark_closes: list[float] | None = None,
    ) -> QuantitativeFeatures:
        closes = [float(price) for price in series.closes]
        volumes = [float(volume) for volume in series.volumes] if series.volumes else []
        cfg = self.config
        ret_1d = window_return(closes, 1)
        ret_5d = window_return(closes, 5)
        ma_short = moving_average(closes, min(cfg.ma_short_window, len(closes))) if closes else None
        ma_long = moving_average(closes, cfg.ma_long_window)
        ma20 = moving_average(closes, cfg.ma20_window)
        ma60 = moving_average(closes, cfg.ma60_window)
        ma120 = moving_average(closes, cfg.ma120_window)
        momentum = None
        if ma_short is not None and ma_long not in (None, 0):
            momentum = ma_short / ma_long - 1.0
        elif ret_5d is not None:
            momentum = ret_5d
        rets = simple_returns(closes[-cfg.vol_window - 1 :] if len(closes) > cfg.vol_window else closes)
        volatility = sample_std(rets)
        drawdown = max_drawdown(closes)
        volume_ratio = None
        if len(volumes) >= 2:
            avg = sum(volumes[:-1]) / len(volumes[:-1])
            if avg > 0:
                volume_ratio = volumes[-1] / avg
        trend = None
        if momentum is not None:
            if momentum > 0.002:
                trend = min(1.0, momentum / 0.05)
            elif momentum < -0.002:
                trend = max(-1.0, momentum / 0.05)
            else:
                trend = 0.0
        relative_strength = None
        if benchmark_closes and len(benchmark_closes) >= 2 and ret_1d is not None:
            bench = window_return(benchmark_closes, 1)
            if bench is not None:
                relative_strength = ret_1d - bench
        time_decay = _series_time_decay(series, as_of, cfg)
        return QuantitativeFeatures(
            return_1d=to_decimal(ret_1d),
            return_5d=to_decimal(ret_5d),
            ma_short=to_decimal(ma_short),
            ma_long=to_decimal(ma_long),
            ma20=to_decimal(ma20),
            ma60=to_decimal(ma60),
            ma120=to_decimal(ma120),
            weekly_trend=None,
            momentum=to_decimal(momentum),
            volatility=to_decimal(volatility),
            drawdown=to_decimal(drawdown),
            volume_ratio=to_decimal(volume_ratio),
            liquidity=to_decimal(liquidity),
            trend=to_decimal(trend),
            relative_strength=to_decimal(relative_strength),
            time_decay=to_decimal(time_decay),
        )


def _series_time_decay(series: PriceSeries, as_of: datetime, cfg: FeaturePolicyConfig) -> float | None:
    if not series.timestamps:
        return None
    last = series.timestamps[-1]
    age = as_of - last
    if age.total_seconds() < 0:
        return 0.0
    half = cfg.market_data_half_life.total_seconds() or 1.0
    return 0.5 ** (age.total_seconds() / half)
