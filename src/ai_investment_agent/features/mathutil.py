from __future__ import annotations

from decimal import Decimal
from math import sqrt


def as_float(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    var = sum((item - avg) ** 2 for item in values) / (len(values) - 1)
    return sqrt(var)


def simple_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for prev, current in zip(closes, closes[1:]):
        if prev == 0:
            continue
        out.append(current / prev - 1.0)
    return out


def window_return(closes: list[float], bars: int) -> float | None:
    if len(closes) < bars + 1 or closes[-(bars + 1)] == 0:
        return None
    return closes[-1] / closes[-(bars + 1)] - 1.0


def moving_average(closes: list[float], window: int) -> float | None:
    if len(closes) < window or window <= 0:
        return None
    return mean(closes[-window:])


def max_drawdown(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak = closes[0]
    worst = 0.0
    for price in closes:
        if price > peak:
            peak = price
        if peak > 0:
            worst = max(worst, (peak - price) / peak)
    return worst


def clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(value, 8)))
