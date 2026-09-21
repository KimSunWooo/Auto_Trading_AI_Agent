from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ai_investment_agent.domain.context import (
    MacroSurprise,
    MarketContext,
    PriceSeries,
)
from ai_investment_agent.domain.event_intelligence import AnalyzedMarketEvent
from ai_investment_agent.features.divergence import DivergenceDetector
from ai_investment_agent.features.event_features import EventFeatureCalculator
from ai_investment_agent.features.macro import MacroSurpriseCalculator
from ai_investment_agent.features.priced_in import HeuristicPricedInAnalyzer
from ai_investment_agent.features.quantitative import QuantitativeFeatureCalculator
from ai_investment_agent.features.regime import FeatureRegimeClassifier
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig
from ai_investment_agent.ports.priced_in import PricedInAnalyzer


class MarketContextEngine:
    """Builds MarketContext from market data and analyzed events. No proposals."""

    def __init__(
        self,
        config: FeaturePolicyConfig | None = None,
        priced_in: PricedInAnalyzer | None = None,
    ) -> None:
        self.config = config or FeaturePolicyConfig()
        self._quant = QuantitativeFeatureCalculator(self.config)
        self._events = EventFeatureCalculator(self.config)
        self._macro = MacroSurpriseCalculator()
        self._priced_in = priced_in or HeuristicPricedInAnalyzer()
        self._divergence = DivergenceDetector()
        self._regime = FeatureRegimeClassifier(self.config)

    def build(
        self,
        *,
        ticker: str,
        as_of: datetime,
        series: PriceSeries | None = None,
        events: list[AnalyzedMarketEvent] | None = None,
        liquidity: float | None = None,
        sectors: list[str] | None = None,
        benchmark_closes: list[float] | None = None,
        macro: MacroSurprise | dict | None = None,
        prior_price_movement: float | None = None,
        post_event_reaction: float | None = None,
        volume_reaction: float | None = None,
        sector_reaction: float | None = None,
        market_reaction: float | None = None,
    ) -> MarketContext:
        path = series or PriceSeries()
        quantitative = self._quant.compute(
            path,
            as_of=as_of,
            liquidity=liquidity,
            benchmark_closes=benchmark_closes,
        )
        event_features = self._events.compute(
            events or [],
            ticker=ticker,
            as_of=as_of,
            sectors=sectors,
        )
        divergences = self._divergence.detect(
            event_features,
            market_reaction=market_reaction if market_reaction is not None else post_event_reaction,
            config=self.config,
        )
        haircut = 0.0
        if divergences:
            haircut = abs(divergences[0].confidence_adjustment)
            event_features = self._events.compute(
                events or [],
                ticker=ticker,
                as_of=as_of,
                sectors=sectors,
                confidence_haircut=haircut,
            )
        priced = None
        impact_sign = _signed_impact(event_features)
        if post_event_reaction is not None or prior_price_movement is not None:
            priced = self._priced_in.analyze(
                event_impact=impact_sign,
                prior_price_movement=prior_price_movement,
                post_event_reaction=post_event_reaction,
                volume_reaction=volume_reaction,
                sector_reaction=sector_reaction,
                market_reaction=market_reaction,
                config=self.config,
            )
        surprise = self._coerce_macro(macro)
        regime = self._regime.classify(
            quantitative,
            event_features,
            as_of=as_of,
            bar_count=len(path.closes),
        )
        return MarketContext(
            ticker=ticker,
            as_of=as_of,
            regime=regime,
            quantitative=quantitative,
            event_features=event_features,
            macro_surprise=surprise,
            priced_in=priced,
            divergences=divergences,
            unknown_treated_as_safe=False,
        )

    def _coerce_macro(self, macro: MacroSurprise | dict | None) -> MacroSurprise | None:
        if macro is None:
            return None
        if isinstance(macro, MacroSurprise):
            return macro
        return self._macro.compute(
            series_id=macro.get("seriesId") or macro.get("series_id"),
            actual=_decimal(macro.get("actual")),
            consensus=_decimal(macro.get("consensus")),
            previous=_decimal(macro.get("previous")),
            historical_std=_decimal(macro.get("historicalStd") or macro.get("historical_std")),
        )


def _signed_impact(features) -> float:
    direction = features.dominant_direction.value
    magnitude = features.effective_impact
    if direction == "NEGATIVE":
        return -magnitude
    if direction == "POSITIVE":
        return magnitude
    return 0.0


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
