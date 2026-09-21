from __future__ import annotations

from ai_investment_agent.domain.context import DivergenceSignal, EventImpactFeatures
from ai_investment_agent.domain.enums import ContextSignal, EventDirection
from ai_investment_agent.policy.feature_config import FeaturePolicyConfig


class DivergenceDetector:
    def detect(
        self,
        events: EventImpactFeatures,
        *,
        market_reaction: float | None,
        config: FeaturePolicyConfig,
    ) -> list[DivergenceSignal]:
        if market_reaction is None:
            return []
        direction = events.dominant_direction
        threshold = config.divergence_move_threshold
        haircut = config.divergence_confidence_haircut
        if direction is EventDirection.POSITIVE and market_reaction <= -threshold:
            return [
                DivergenceSignal(
                    code=ContextSignal.EVENT_MARKET_DIVERGENCE,
                    event_direction=direction,
                    market_reaction=market_reaction,
                    confidence_adjustment=-haircut,
                    explanation="Positive event with strong negative market reaction.",
                )
            ]
        if direction is EventDirection.NEGATIVE and market_reaction >= threshold:
            return [
                DivergenceSignal(
                    code=ContextSignal.EVENT_MARKET_DIVERGENCE,
                    event_direction=direction,
                    market_reaction=market_reaction,
                    confidence_adjustment=-haircut,
                    explanation="Negative event with strong positive market reaction.",
                )
            ]
        return []
