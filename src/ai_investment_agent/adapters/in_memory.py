from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from ai_investment_agent.domain.decision import DecisionSnapshot
from ai_investment_agent.domain.evaluation import CounterfactualOutcome
from ai_investment_agent.domain.journal import DecisionJournalEntry
from ai_investment_agent.domain.proposal import TradeProposal


class InMemoryDecisionRepository:
    def __init__(self) -> None:
        self._snapshots: dict[str, DecisionSnapshot] = {}
        self._journal: dict[str, list[DecisionJournalEntry]] = defaultdict(list)
        self._order: list[str] = []

    def save_snapshot(self, snapshot: DecisionSnapshot) -> None:
        if snapshot.decision_id not in self._snapshots:
            self._order.append(snapshot.decision_id)
        self._snapshots[snapshot.decision_id] = snapshot

    def get_snapshot(self, decision_id: str) -> DecisionSnapshot | None:
        return self._snapshots.get(decision_id)

    def list_snapshots(self) -> Sequence[DecisionSnapshot]:
        return tuple(self._snapshots[key] for key in self._order if key in self._snapshots)

    def save_journal_entry(self, entry: DecisionJournalEntry) -> None:
        self._journal[entry.decision_id].append(entry)

    def list_journal(self, decision_id: str) -> Sequence[DecisionJournalEntry]:
        return tuple(self._journal.get(decision_id, ()))

    def attach_counterfactual(
        self, decision_id: str, outcome: CounterfactualOutcome
    ) -> DecisionSnapshot | None:
        current = self._snapshots.get(decision_id)
        if current is None:
            return None
        updated = current.model_copy(update={"counterfactual": outcome})
        self._snapshots[decision_id] = updated
        return updated


class InMemoryDecisionPublisher:
    """Stores proposals in process. Does not send orders."""

    def __init__(self) -> None:
        self.published: list[TradeProposal] = []

    def publish(self, proposal: TradeProposal) -> None:
        self.published.append(proposal)
