from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai_investment_agent.domain.collection import CollectionTimestamps

FIXED_AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def make_timestamps(
    available_at: datetime,
    *,
    event_occurred_at: datetime | None = None,
    extra_collect_lag: timedelta = timedelta(seconds=1),
) -> CollectionTimestamps:
    published = available_at
    received = available_at
    collected = available_at + extra_collect_lag
    return CollectionTimestamps(
        event_occurred_at=event_occurred_at or available_at,
        published_at=published,
        source_received_at=received,
        collected_at=collected,
        normalized_at=collected,
        analyzed_at=collected + timedelta(seconds=1),
        tradable_at=available_at,
    )
