from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.journal import DecisionJournalEntry
from ai_investment_agent.domain.proposal import TradeProposal


class InMemoryDecisionRepository:
    def __init__(self) -> None:
        self._snapshots: dict[str, DecisionSnapshot] = {}
        self._journal: dict[str, list[DecisionJournalEntry]] = defaultdict(list)

    def save_snapshot(self, snapshot: DecisionSnapshot) -> None:
        self._snapshots[snapshot.decision_id] = snapshot

    def get_snapshot(self, decision_id: str) -> DecisionSnapshot | None:
        return self._snapshots.get(decision_id)

    def save_journal_entry(self, entry: DecisionJournalEntry) -> None:
        self._journal[entry.decision_id].append(entry)

    def list_journal(self, decision_id: str) -> Sequence[DecisionJournalEntry]:
        return tuple(self._journal.get(decision_id, ()))


class InMemoryDecisionPublisher:
    """Stores proposals in process. Does not send orders."""

    def __init__(self) -> None:
        self.published: list[TradeProposal] = []

    def publish(self, proposal: TradeProposal) -> None:
        self.published.append(proposal)
