"""Source trust tiers. Hard-coded policy, not inferred from document text."""

from __future__ import annotations

from ai_investment_agent.domain.enums import SourceTier

TIER_SCORES: dict[SourceTier, float] = {
    SourceTier.S: 1.00,
    SourceTier.A: 0.85,
    SourceTier.B: 0.70,
    SourceTier.C: 0.45,
    SourceTier.D: 0.20,
}

# Longer keys first so "federalreserve.gov" wins over a short fragment.
_TIER_S = (
    "dart.fss.or.kr",
    "fss.or.kr",
    "dart",
    "bok.or.kr",
    "bankofkorea",
    "federalreserve.gov",
    "federalreserve",
    "ecb.europa.eu",
    "sec.gov",
    "kostat.go.kr",
    "bls.gov",
    "imf.org",
    "oecd.org",
)
_TIER_A = (
    "reuters",
    "bloomberg",
    "yonhap",
    "yna.co.kr",
    "associated press",
    "ap.org",
)
_TIER_B = (
    "wsj",
    "ft.com",
    "financial times",
    "hankyung",
    "hankyung.com",
    "korea economic daily",
    "maeil",
    "mk.co.kr",
    "nikkei",
)
_TIER_C = (
    "news",
    "times",
    "herald",
    "press",
    "daily",
)
_TIER_D = (
    "twitter",
    "x.com",
    "facebook",
    "telegram",
    "discord",
    "reddit",
    "dcinside",
    "cafe.naver",
    "blog",
    "community",
    "sns",
    "rumor",
    "unverified",
)


def canonical_source_key(source: str) -> str:
    return " ".join(source.lower().strip().replace("_", " ").split())


def source_tier_for(source: str) -> SourceTier:
    key = canonical_source_key(source)
    for fragment in _TIER_D:
        if fragment in key:
            return SourceTier.D
    for fragment in _TIER_S:
        if fragment in key:
            return SourceTier.S
    for fragment in _TIER_A:
        if fragment in key:
            return SourceTier.A
    for fragment in _TIER_B:
        if fragment in key:
            return SourceTier.B
    for fragment in _TIER_C:
        if fragment in key:
            return SourceTier.C
    return SourceTier.D


def source_trust_score(source: str) -> float:
    return TIER_SCORES[source_tier_for(source)]


def cluster_source_trust(sources: list[str]) -> tuple[SourceTier, float]:
    if not sources:
        return SourceTier.D, TIER_SCORES[SourceTier.D]
    tiers = [source_tier_for(source) for source in sources]
    best = min(tiers, key=lambda tier: "SABCD".index(tier.value))
    return best, TIER_SCORES[best]
