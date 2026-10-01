"""Analysis clocks. Live defaults to timezone-aware UTC now; FIXTURE stays pinned."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_investment_agent.domain.enums import DataMode
from ai_investment_agent.domain.runtime import RuntimeSettings

FIXTURE_AS_OF = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


def utc_now() -> datetime:
    """Wall-clock UTC. Used as the Live default analysis/judgment clock."""
    return datetime.now(UTC)


def default_now_fn(runtime: RuntimeSettings):
    """FIXTURE/REPLAY stay reproducible. LIVE uses current UTC unless injected."""
    if runtime.data_mode in {DataMode.LIVE_OBSERVATION, DataMode.LIVE_SHADOW}:
        return utc_now
    return lambda: FIXTURE_AS_OF
