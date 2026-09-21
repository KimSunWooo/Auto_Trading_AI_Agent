"""Proposal freshness TTL. This is judgment-artifact metadata, not an order TTL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ai_investment_agent.domain.enums import Horizon


@dataclass(frozen=True)
class ProposalFreshnessPolicy:
    short_term: timedelta = timedelta(hours=4)
    long_term: timedelta = timedelta(days=5)
    none: timedelta = timedelta(hours=1)

    def ttl_for(self, horizon: Horizon) -> timedelta:
        if horizon is Horizon.SHORT_TERM:
            return self.short_term
        if horizon is Horizon.LONG_TERM:
            return self.long_term
        return self.none

    def valid_until(self, *, generated_at: datetime, horizon: Horizon) -> datetime:
        return generated_at + self.ttl_for(horizon)
