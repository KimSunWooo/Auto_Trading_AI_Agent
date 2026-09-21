"""Policy package. Hard gates live here so adapters cannot bypass them easily."""

from ai_investment_agent.policy.gates import GateResult, apply_hard_gates
from ai_investment_agent.policy.priorities import PRIORITY_ORDER

__all__ = ["GateResult", "PRIORITY_ORDER", "apply_hard_gates"]
