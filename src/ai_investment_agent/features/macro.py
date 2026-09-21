from __future__ import annotations

from decimal import Decimal

from ai_investment_agent.domain.context import MacroSurprise


class MacroSurpriseCalculator:
    """Computes surprise only when actual and consensus are both present."""

    def compute(
        self,
        *,
        series_id: str | None = None,
        actual: Decimal | None = None,
        consensus: Decimal | None = None,
        previous: Decimal | None = None,
        historical_std: Decimal | None = None,
    ) -> MacroSurprise:
        missing: list[str] = []
        if actual is None:
            missing.append("actual")
        if consensus is None:
            missing.append("consensus")
        if previous is None:
            missing.append("previous")
        surprise: Decimal | None = None
        z_score: Decimal | None = None
        if actual is not None and consensus is not None:
            surprise = actual - consensus
            if historical_std is not None and historical_std != 0:
                z_score = surprise / historical_std
        elif historical_std is None:
            missing.append("historicalStd")
        return MacroSurprise(
            series_id=series_id,
            actual=actual,
            consensus=consensus,
            previous=previous,
            surprise=surprise,
            surprise_z_score=z_score,
            historical_std=historical_std,
            missing_fields=missing,
        )
