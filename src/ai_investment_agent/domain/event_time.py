"""Event time semantics. analyzedAt is never used as market availability."""

from __future__ import annotations

from datetime import datetime


def resolve_market_available_at(
    *,
    published_at: datetime | None = None,
    source_received_at: datetime | None = None,
    collected_at: datetime | None = None,
) -> datetime | None:
    """Earliest known time the information could be used in the market.

    Preference is not guessed: only provided timestamps participate.
    analyzedAt is intentionally absent from this function.
    """

    known = [item for item in (published_at, source_received_at, collected_at) if item is not None]
    if not known:
        return None
    return min(known)


def event_occurred_for_market(
    *,
    occurred_at: datetime | None,
    market_available_at: datetime | None,
    published_at: datetime | None,
    source_received_at: datetime | None,
    collected_at: datetime | None,
    analyzed_at: datetime,
) -> datetime:
    """Judgment-layer MarketEvent.occurredAt. Never prefers analyzedAt."""

    for value in (
        occurred_at,
        market_available_at,
        published_at,
        source_received_at,
        collected_at,
    ):
        if value is not None:
            return value
    return analyzed_at
