"""Analysis clocks. Live defaults to timezone-aware UTC now; FIXTURE stays pinned.

Time roles (do not collapse these):
- request_at: when evaluate starts a collection cycle
- query as_of: provider query window / explicit historical cutoff
- sourceReceivedAt: when this process actually observed the payload
- judgment cutoff / analysis_as_of: accessibility horizon used for the decision
- generated_at: when the TradeProposal is created

Live current observation (as_of omitted) uses a cutoff at or after the
last receive in the cycle so in-cycle data is usable. An explicit past
as_of never sees rows received after that cutoff. Provider timestamps
are evidence from the vendor; sourceReceivedAt is our observation clock.
"""

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
