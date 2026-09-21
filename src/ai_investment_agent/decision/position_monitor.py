from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.agent_views import FixturePosition
from ai_investment_agent.domain.enums import PositionThesisStatus


class PositionThesisMonitor:
    """Watches an existing (fixture) position thesis. Does not open orders."""

    def inspect(self, position: FixturePosition | None) -> PositionThesisStatus:
        if position is None or position.quantity == Decimal("0"):
            return PositionThesisStatus.NO_POSITION
        if position.triggered_invalidations:
            return PositionThesisStatus.EXIT_REVIEW
        return PositionThesisStatus.THESIS_INTACT
