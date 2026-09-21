from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TypeVar

from ai_investment_agent.domain.collection import CollectionTimestamps, is_accessible_at

T = TypeVar("T")


def accessible_as_of(
    records: Sequence[T],
    as_of: datetime,
    *,
    timestamps_of=lambda record: record.timestamps,
) -> list[T]:
    """Replay/backtest view: keep only records actually accessible at as_of."""
    accessible: list[T] = []
    for record in records:
        timestamps: CollectionTimestamps = timestamps_of(record)
        if is_accessible_at(timestamps, as_of):
            accessible.append(record)
    return accessible


class AsOfView:
    def __init__(self, as_of: datetime) -> None:
        self.as_of = as_of

    def take(self, records: Sequence[T], *, timestamps_of=lambda record: record.timestamps) -> list[T]:
        return accessible_as_of(records, self.as_of, timestamps_of=timestamps_of)
