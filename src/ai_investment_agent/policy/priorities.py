"""Ordered agent priorities. Return-seeking never outranks preservation."""

from ai_investment_agent.domain.enums import AgentPriority

PRIORITY_ORDER: tuple[AgentPriority, ...] = (
    AgentPriority.CAPITAL_PRESERVATION,
    AgentPriority.CATASTROPHIC_LOSS_PREVENTION,
    AgentPriority.RISK_ADJUSTED_RETURN,
    AgentPriority.STABLE_JUDGMENT,
    AgentPriority.OPPORTUNITY_SEEKING,
)
