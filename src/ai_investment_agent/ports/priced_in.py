from __future__ import annotations

from typing import Protocol

from ai_investment_agent.domain.context import PricedInAnalysis
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig


class PricedInAnalyzer(Protocol):
    """Replaceable priced-in estimator. Heuristic today, model later."""

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
        ...
