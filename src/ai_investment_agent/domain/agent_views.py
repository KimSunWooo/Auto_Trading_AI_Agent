"""Long/short feature views and assessments. Missing values stay None."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from ai_investment_agent.domain.base import DomainModel
from ai_investment_agent.domain.context import PriceSeries
from ai_investment_agent.domain.enums import (
    EntryTiming,
    Horizon,
    HorizonChoice,
    PositionThesisStatus,
    Stance,
)


class LongTermFeatures(DomainModel):
    daily_trend: Decimal | None = None
    weekly_trend: Decimal | None = None
    ma20: Decimal | None = None
    ma60: Decimal | None = None
    ma120: Decimal | None = None
    last_price: Decimal | None = None
    momentum: Decimal | None = None
    drawdown: Decimal | None = None
    fundamentals_score: Decimal | None = None
    valuation_score: Decimal | None = None
    sector_strength: Decimal | None = None
    macro_risk: Decimal | None = None
    long_horizon_event_bias: Decimal | None = None
    volatility: Decimal | None = None


class ShortTermFeatures(DomainModel):
    """Intraday fields are optional when the feed does not exist yet."""

    intraday_trend: Decimal | None = None
    ohlcv_1m: PriceSeries | None = None
    ohlcv_5m: PriceSeries | None = None
    ohlcv_15m: PriceSeries | None = None
    vwap: Decimal | None = None
    volume_spike: Decimal | None = None
    momentum: Decimal | None = None
    breakout: Decimal | None = None
    volatility: Decimal | None = None
    liquidity: Decimal | None = None
    spread: Decimal | None = None
    short_lived_event_bias: Decimal | None = None
    last_price: Decimal | None = None


class UtilityBreakdown(DomainModel):
    expected_return: Decimal | None = None
    risk_penalty: Decimal = Decimal("0")
    transaction_cost: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    drawdown_penalty: Decimal = Decimal("0")
    tail_risk: Decimal = Decimal("0")
    uncertainty_penalty: Decimal = Decimal("0")
    net_edge: Decimal | None = None


class AgentAssessment(DomainModel):
    horizon: Horizon
    stance: Stance
    confidence: float = Field(ge=0, le=1)
    utility: UtilityBreakdown
    drivers: list[str] = Field(default_factory=list)
    invalidations: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)

    @property
    def net_edge(self) -> Decimal | None:
        return self.utility.net_edge


class EntrySnapshot(DomainModel):
    extension_vs_ma: Decimal | None = None
    already_priced_in: float | None = None
    remaining_edge: float | None = None
    vwap_distance: Decimal | None = None
    liquidity: Decimal | None = None


class FixturePosition(DomainModel):
    """Test/fixture position only. Not a live brokerage account."""

    ticker: str = Field(min_length=1)
    quantity: Decimal = Decimal("0")
    average_price: Decimal | None = None
    thesis_drivers: list[str] = Field(default_factory=list)
    thesis_invalidations: list[str] = Field(default_factory=list)
    triggered_invalidations: list[str] = Field(default_factory=list)


class HorizonDecision(DomainModel):
    choice: HorizonChoice
    long_stance: Stance
    short_stance: Stance
    long_net_edge: Decimal | None = None
    short_net_edge: Decimal | None = None
    entry_timing: EntryTiming = EntryTiming.NOT_APPLICABLE
    position_status: PositionThesisStatus = PositionThesisStatus.NO_POSITION
    reason_codes: list[str] = Field(default_factory=list)
