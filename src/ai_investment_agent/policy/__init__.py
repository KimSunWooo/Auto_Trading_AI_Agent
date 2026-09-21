"""Policy package. Hard gates live here so adapters cannot bypass them easily."""

from ai_investment_agent.policy.utility import UtilityConfig
from ai_investment_agent.policy.feature_config import EventImpactWeights, FeaturePolicyConfig
from ai_investment_agent.policy.gates import GateResult, apply_hard_gates
from ai_investment_agent.policy.priorities import PRIORITY_ORDER
from ai_investment_agent.policy.source_trust import (
    source_tier_for,
    source_trust_score,
)

__all__ = [
    "EventImpactWeights",
    "FeaturePolicyConfig",
    "GateResult",
    "PRIORITY_ORDER",
    "apply_hard_gates",
    "source_tier_for",
    "source_trust_score",
    "UtilityConfig",
]
