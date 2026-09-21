from __future__ import annotations

from ai_investment_agent.domain.context import PricedInAnalysis
from ai_investment_agent.features.mathutil import clip01
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig


class HeuristicPricedInAnalyzer:
    """Same-direction reaction / impact. Swap via PricedInAnalyzer port later."""

    def analyze(
        self,
        *,
        event_impact: float,
        prior_price_movement: float | None,
        post_event_reaction: float | None,
        volume_reaction: float | None,
        sector_reaction: float | None,
        market_reaction: float | None,
        config: FeaturePolicyConfig,
    ) -> PricedInAnalysis:
        already: float | None = None
        remaining: float | None = None
        if post_event_reaction is not None and event_impact != 0:
            same_direction = (event_impact * post_event_reaction) > 0
            if same_direction:
                absorbed = min(1.0, abs(post_event_reaction) / abs(event_impact))
                volume_term = clip01(abs(volume_reaction)) if volume_reaction is not None else 0.0
                already = clip01(
                    absorbed * config.priced_in_reaction_weight
                    + volume_term * config.priced_in_volume_weight
                )
                remaining = clip01(1.0 - already)
            else:
                already = 0.0
                remaining = clip01(abs(event_impact))
        return PricedInAnalysis(
            event_impact=event_impact,
            prior_price_movement=prior_price_movement,
            post_event_reaction=post_event_reaction,
            volume_reaction=volume_reaction,
            sector_reaction=sector_reaction,
            market_reaction=market_reaction,
            already_priced_in=already,
            remaining_edge=remaining,
            method="heuristic_v1",
        )
