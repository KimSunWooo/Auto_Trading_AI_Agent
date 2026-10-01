from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TypeVar

from ai_investment_agent.domain.collection import (
    CollectionResult,
    CollectionTimestamps,
    is_accessible_at,
    is_stale,
)
from ai_investment_agent.domain.enums import CollectionStatus, FreshnessClass

T = TypeVar("T")


def collect_accessible(
    records: Sequence[T],
    *,
    as_of: datetime,
    unavailable: bool,
    unavailable_reason: str,
    match: Callable[[T], bool],
    timestamps_of: Callable[[T], CollectionTimestamps],
    freshness_of: Callable[[T], FreshnessClass],
    id_of: Callable[[T], str],
    empty_status: CollectionStatus,
    empty_error: str | None = None,
    reject_future_event_occurred: bool = False,
) -> CollectionResult[T]:
    """Shared collection query. Empty success is never returned as OK.

    ``reject_future_event_occurred`` is Live-only. Fixture/replay calendar rows
    may describe a future eventOccurredAt that was already published; those
    collectors keep the default (False) so this flag does not change them.
    """
    if unavailable:
        return CollectionResult.unavailable(error=unavailable_reason, as_of=as_of)

    matched: list[T] = []
    for record in records:
        if not match(record):
            continue
        timestamps = timestamps_of(record)
        if not is_accessible_at(timestamps, as_of):
            continue
        if (
            reject_future_event_occurred
            and timestamps.event_occurred_at is not None
            and timestamps.event_occurred_at > as_of
        ):
            continue
        matched.append(record)

    if not matched:
        if empty_status is CollectionStatus.NO_EVENT:
            return CollectionResult.no_event(as_of=as_of)
        reason = empty_error or unavailable_reason
        return CollectionResult.unavailable(error=reason, as_of=as_of)

    stale_ids = [
        id_of(record)
        for record in matched
        if is_stale(timestamps_of(record), as_of, freshness_of(record))
    ]
    classes = {freshness_of(record) for record in matched}
    freshness = next(iter(classes)) if len(classes) == 1 else None
    if stale_ids and len(stale_ids) == len(matched):
        return CollectionResult.stale(
            list(matched),
            as_of=as_of,
            freshness_class=freshness,
            stale_item_ids=stale_ids,
        )
    return CollectionResult.ok(
        list(matched),
        as_of=as_of,
        freshness_class=freshness,
        stale_item_ids=stale_ids,
    )
