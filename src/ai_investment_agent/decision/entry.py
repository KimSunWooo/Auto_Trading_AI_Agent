from __future__ import annotations

from ai_investment_agent.domain.agent_views import EntrySnapshot
from ai_investment_agent.domain.enums import EntryTiming, HorizonChoice, ReasonCode
from ai_investment_agent.policy.utility import UtilityConfig


class EntryAnalyzer:
    """Timing of a new entry. Independent from whether the position thesis is valid."""

    def __init__(self, config: UtilityConfig | None = None) -> None:
        self.config = config or UtilityConfig()

    def timing(self, choice: HorizonChoice, snapshot: EntrySnapshot | None) -> tuple[EntryTiming, list[str]]:
        if choice not in {HorizonChoice.LONG_TERM, HorizonChoice.SHORT_TERM}:
            return EntryTiming.NOT_APPLICABLE, []
        if snapshot is None:
            return EntryTiming.WAIT, [ReasonCode.ENTRY_CONTEXT_MISSING.value, ReasonCode.ENTRY_WAIT.value]

        reasons: list[str] = []
        stretched = (
            snapshot.extension_vs_ma is not None
            and snapshot.extension_vs_ma >= self.config.stretched_extension
        )
        priced = (
            snapshot.already_priced_in is not None
            and snapshot.already_priced_in >= self.config.priced_in_wait
        )
        thin_edge = (
            snapshot.remaining_edge is not None
            and snapshot.remaining_edge <= self.config.remaining_edge_wait
        )
        if stretched or priced or thin_edge:
            reasons.append(ReasonCode.POOR_ENTRY.value)
            reasons.append(ReasonCode.ENTRY_WAIT.value)
            return EntryTiming.WAIT, reasons
        return EntryTiming.BUY_NOW, []
