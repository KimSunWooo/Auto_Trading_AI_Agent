from __future__ import annotations

from ai_investment_agent.domain.enums import SourceTier, VerificationStatus
from ai_investment_agent.domain.event_intelligence import EventCluster, NormalizedEvent
from ai_investment_agent.policy.source_trust import canonical_source_key, source_tier_for

_INDEPENDENT_MIN_VERIFIED = 2


class EventVerifier:
    def verify(
        self,
        cluster: EventCluster,
        members: list[NormalizedEvent],
    ) -> VerificationStatus:
        if any(member.looks_like_retraction for member in members):
            return VerificationStatus.RETRACTED

        sources = [canonical_source_key(member.source) for member in members]
        independent = set(sources)
        tiers = [source_tier_for(member.source) for member in members]

        if SourceTier.S in tiers:
            return VerificationStatus.VERIFIED
        if len(independent) >= _INDEPENDENT_MIN_VERIFIED and (
            SourceTier.A in tiers or SourceTier.B in tiers
        ):
            return VerificationStatus.VERIFIED
        if len(independent) >= _INDEPENDENT_MIN_VERIFIED:
            return VerificationStatus.PARTIALLY_VERIFIED
        if SourceTier.A in tiers:
            return VerificationStatus.PARTIALLY_VERIFIED
        return VerificationStatus.UNVERIFIED
